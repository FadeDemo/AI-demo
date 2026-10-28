import asyncio
import logging
import re
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch

from prompt_toolkit.input import create_pipe_input

from llm_terminal_assistant.adapter.fake_client import FakeClient
from llm_terminal_assistant.adapter.fake_model import (
    CodePointTokenCounter,
    FakeModelRequestEncoder,
)
from llm_terminal_assistant.budgeter import Budgeter
from llm_terminal_assistant.cli import send_stream_conversation_turn, talk
from llm_terminal_assistant.config import (
    ModelConfig,
    RequestRetryConfig,
    RequestTimeoutConfig,
)
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import (
    FAKE_MODEL_PROFILE,
    InputTokensDetails,
    ModelLimits,
    ModelResponseEndReason,
    ModelResponseError,
    ModelResponseIncompleteDetails,
    ModelUsage,
    OutputTokensDetails,
)
from llm_terminal_assistant.stream.events import EndEvent, TextDeltaEvent, UsageEvent


def failed_event(reason, retry_after=None):
    return EndEvent(
        reason,
        ModelResponseError(reason, "Service request failed.", retry_after),
        None,
    )


class StreamRetryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = 100.0
        self.displayed = []
        self.config = ModelConfig(
            api_key="",
            base_url="",
            model="fake-model",
            model_profile=FAKE_MODEL_PROFILE,
        )
        self.budgeter = Budgeter(
            token_counter=CodePointTokenCounter(),
            request_encoder=FakeModelRequestEncoder(),
            model_limits=ModelLimits(context_window_tokens=100_000),
            safety_margin_tokens=0,
        )
        self.usage = ModelUsage(
            20, InputTokensDetails(0, 0), 5, OutputTokensDetails(0), 25
        )
        self.completed = EndEvent(ModelResponseEndReason.COMPLETED_NORMALLY, None, None)
        self.sleep = AsyncMock(side_effect=self.advance_time)
        self.uniform = Mock(side_effect=lambda low, high: high / 2)

    async def advance_time(self, delay):
        self.now += delay

    async def run_turn(self, client, **overrides):
        options = {
            "client": client,
            "budgeter": self.budgeter,
            "system_message": Message("system", "You are a helpful assistant."),
            "completed_turns": [],
            "current_user_message": Message("user", "question"),
            "reserved_output_tokens": 128,
            "min_reserved_recent_turns": 1,
            "display_text": self.displayed.append,
            "clock": lambda: self.now,
            "request_retry_config": self.config.request_retry_config,
            "sleep": self.sleep,
            "uniform": self.uniform,
        }
        options.update(overrides)
        return await send_stream_conversation_turn(**options)

    def scripted_client(self, attempts, *, read_seconds=0.0, close_seconds=0.0):
        client = FakeClient(self.config)
        steps = []

        async def stream(request):
            attempt = len(client.requests) + 1
            if attempt > 1:
                self.assertEqual(steps[-1], ("closed", attempt - 1))
            client.requests.append(request)
            steps.append(("send", attempt))
            try:
                for event in attempts[attempt - 1]:
                    self.now += read_seconds
                    if isinstance(event, Exception):
                        raise event
                    yield event
                steps.append(("tail read", attempt))
            finally:
                self.now += close_seconds
                steps.append(("closed", attempt))

        self.enterContext(patch.object(client, "send_stream", side_effect=stream))
        return client, steps

    def attempt_log_fields(self, captured):
        attempts = []
        for record in captured.records:
            message = record.getMessage()
            if not message.startswith(
                ("Begin to attempt to send request:", "Attempt finished:")
            ):
                continue
            fields = dict(
                re.findall(r"\b(request_id|attempt|reason)=([^\s,]+)", message)
            )
            if "request_id" in fields:
                self.assertEqual(record.levelno, logging.INFO)
                self.assertRegex(fields["request_id"], r"^[0-9a-f]{32}$")
                self.assertIn("attempt", fields)
                attempts.append(fields)
        return attempts

    def wait_log_fields(self, captured):
        waits = []
        for record in captured.records:
            message = record.getMessage()
            if not message.startswith("Expected to wait for "):
                continue
            delay_match = re.match(r"Expected to wait for (\S+) seconds:", message)
            self.assertIsNotNone(delay_match)
            self.assertEqual(record.levelno, logging.INFO)
            fields = dict(
                re.findall(r"\b(request_id|attempt|reason)=([^\s,]+)", message)
            )
            self.assertEqual(set(fields), {"request_id", "attempt", "reason"})
            fields["planned_delay_seconds"] = float(delay_match[1])
            waits.append(fields)
        return waits

    def finished_attempt_log_fields(self, captured):
        return [
            dict(re.findall(r"\b(\w+)=([^\s,]+)", record.getMessage()))
            for record in captured.records
            if record.getMessage().startswith("Attempt finished:")
        ]

    def assert_final_log(
        self, captured, *, attempts, reason, ttft_seconds, total_seconds
    ):
        records = [
            record
            for record in captured.records
            if record.getMessage().startswith("Request finished:")
        ]
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertIs(record, captured.records[-1])
        self.assertEqual(record.levelno, logging.INFO)
        fields = dict(re.findall(r"\b(\w+)=([^\s,]+)", record.getMessage()))
        request_id = fields["request_id"]
        self.assertRegex(request_id, r"^[0-9a-f]{32}$")
        self.assertEqual(
            fields,
            {
                "request_id": request_id,
                "attempts": str(attempts),
                "reason": str(reason),
                "ttft_seconds": str(ttft_seconds),
                "total_seconds": str(total_seconds),
            },
        )
        for attempt in self.attempt_log_fields(captured):
            self.assertEqual(attempt["request_id"], request_id)

    async def test_attempt_logs_follow_execution_without_recording_payloads(self):
        prompt = "TEST_PROMPT_NOT_FOR_LOGS"
        body = "TEST_BODY_NOT_FOR_LOGS"
        credential = "FAKE_CREDENTIAL_NOT_FOR_LOGS"
        raw_error = "TEST_SERVICE_ERROR_NOT_FOR_LOGS"
        client = FakeClient(replace(self.config, api_key=credential))
        steps = []

        async def stream(request):
            attempt = len(client.requests) + 1
            client.requests.append(request)
            fields = self.attempt_log_fields(captured)
            self.assertEqual(len(fields), attempt * 2 - 1)
            self.assertEqual(fields[-1]["attempt"], str(attempt))
            self.assertNotIn("reason", fields[-1])
            steps.append(("send", attempt))
            try:
                if attempt == 1:
                    yield EndEvent(
                        ModelResponseEndReason.RATE_LIMITED,
                        ModelResponseError("rate_limited", raw_error),
                        None,
                    )
                else:
                    yield TextDeltaEvent(body)
                    yield UsageEvent(self.usage)
                    yield self.completed
            finally:
                # 流完成清理前，不得提前记录本次尝试已结束。
                self.assertEqual(
                    len(self.attempt_log_fields(captured)), attempt * 2 - 1
                )
                self.assertFalse(
                    any(
                        record.getMessage().startswith("Request finished:")
                        for record in captured.records
                    )
                )
                steps.append(("closed", attempt))

        async def wait(delay):
            self.assertEqual(steps, [("send", 1), ("closed", 1)])
            fields = self.attempt_log_fields(captured)
            self.assertEqual(len(fields), 2)
            self.assertEqual(fields[-1]["reason"], "rate_limited")
            self.assertEqual(
                self.wait_log_fields(captured),
                [{**fields[-1], "planned_delay_seconds": delay}],
            )
            await self.advance_time(delay)

        with (
            self.assertLogs("llm_terminal_assistant.cli", level="INFO") as captured,
            patch.object(client, "send_stream", side_effect=stream),
        ):
            response, _ = await self.run_turn(
                client,
                current_user_message=Message("user", prompt),
                sleep=wait,
            )

        self.assertEqual(len(client.requests), 2)
        self.assertEqual(response.text, body)
        fields = self.attempt_log_fields(captured)
        request_id = fields[0]["request_id"]
        self.assertEqual(
            fields,
            [
                {"request_id": request_id, "attempt": "1"},
                {"request_id": request_id, "attempt": "1", "reason": "rate_limited"},
                {"request_id": request_id, "attempt": "2"},
                {
                    "request_id": request_id,
                    "attempt": "2",
                    "reason": "completed_normally",
                },
            ],
        )
        self.assertEqual(
            steps, [("send", 1), ("closed", 1), ("send", 2), ("closed", 2)]
        )
        self.assertEqual(
            self.finished_attempt_log_fields(captured),
            [
                {
                    **fields[1],
                    "input_tokens": "None",
                    "output_tokens": "None",
                    "total_tokens": "None",
                },
                {
                    **fields[3],
                    "input_tokens": "20",
                    "output_tokens": "5",
                    "total_tokens": "25",
                },
            ],
        )
        self.assert_final_log(
            captured,
            attempts=2,
            reason=ModelResponseEndReason.COMPLETED_NORMALLY,
            ttft_seconds=0.5,
            total_seconds=0.5,
        )
        for record in captured.records:
            self.assertIsNone(record.exc_info)
            for private_value in (prompt, body, credential, raw_error):
                self.assertNotIn(private_value, record.getMessage())

    async def test_attempt_usage_logs_preserve_reported_counts(self):
        for input_tokens, output_tokens, total_tokens in (
            (20, 5, 25),
            (0, 0, 0),
            (20, 0, 20),
        ):
            with self.subTest(counts=(input_tokens, output_tokens, total_tokens)):
                usage = replace(
                    self.usage,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                )
                client, _ = self.scripted_client([[UsageEvent(usage), self.completed]])
                with self.assertLogs(
                    "llm_terminal_assistant.cli", level="INFO"
                ) as captured:
                    response, _ = await self.run_turn(client)

                self.assertEqual(len(client.requests), 1)
                self.assertIs(response.usage, usage)
                self.assertEqual(
                    self.finished_attempt_log_fields(captured),
                    [
                        {
                            **self.attempt_log_fields(captured)[-1],
                            "input_tokens": str(input_tokens),
                            "output_tokens": str(output_tokens),
                            "total_tokens": str(total_tokens),
                        }
                    ],
                )

    async def test_retryable_failures_recover_through_stream_turn(self):
        for reason in (
            ModelResponseEndReason.CONNECTION_FAILED,
            ModelResponseEndReason.CONNECTION_TIMEOUT,
            ModelResponseEndReason.READ_TIMEOUT,
            ModelResponseEndReason.FIRST_EVENT_TIMEOUT,
            ModelResponseEndReason.STREAM_IDLE_TIMEOUT,
            ModelResponseEndReason.RATE_LIMITED,
            ModelResponseEndReason.SERVICE_UNAVAILABLE,
        ):
            with self.subTest(reason=reason):
                self.sleep.reset_mock()
                self.displayed.clear()
                client, steps = self.scripted_client(
                    [[failed_event(reason)], [TextDeltaEvent("answer"), self.completed]]
                )
                with patch.object(
                    self.budgeter, "check", wraps=self.budgeter.check
                ) as check:
                    response, trim_result = await self.run_turn(client)

                check.assert_called_once_with(trim_result.request)
                self.assertEqual(len(client.requests), 2)
                self.assertTrue(
                    all(request is trim_result.request for request in client.requests)
                )
                self.assertEqual(
                    steps, [("send", 1), ("closed", 1), ("send", 2), ("closed", 2)]
                )
                self.sleep.assert_awaited_once_with(0.5)
                self.assertEqual(
                    response.reason, ModelResponseEndReason.COMPLETED_NORMALLY
                )
                self.assertIsNone(response.error)
                self.assertEqual(response.text, "answer")
                self.assertEqual(self.displayed, ["answer"])

    async def test_backoff_server_hint_and_all_attempts_share_timing_and_request(self):
        client, steps = self.scripted_client(
            [
                [failed_event(ModelResponseEndReason.READ_TIMEOUT)],
                [failed_event(ModelResponseEndReason.RATE_LIMITED, 5.0)],
                [failed_event(ModelResponseEndReason.SERVICE_UNAVAILABLE, 0.0)],
                [TextDeltaEvent("answer"), UsageEvent(self.usage), self.completed],
            ],
            read_seconds=1.0,
            close_seconds=0.5,
        )
        check_budget = self.budgeter.check

        def prepare(request):
            self.now += 2.0
            return check_budget(request)

        with (
            patch.object(self.budgeter, "check", side_effect=prepare) as check,
            self.assertLogs("llm_terminal_assistant.cli", level="INFO") as captured,
        ):
            response, trim_result = await self.run_turn(
                client,
                request_retry_config=RequestRetryConfig(4, 2.0, 3.0),
                request_timeout_config=RequestTimeoutConfig(10, 30, 30, 120),
            )

        check.assert_called_once_with(trim_result.request)
        attempts = self.attempt_log_fields(captured)
        request_id = attempts[0]["request_id"]
        self.assertEqual(
            self.wait_log_fields(captured),
            [
                {
                    "request_id": request_id,
                    "attempt": str(attempt),
                    "reason": reason,
                    "planned_delay_seconds": delay,
                }
                for attempt, reason, delay in (
                    (1, "read_timeout", 1.0),
                    (2, "rate_limited", 5.0),
                    (3, "service_unavailable", 1.5),
                )
            ],
        )
        self.uniform.assert_has_calls([call(0, 2.0), call(0, 3.0), call(0, 3.0)])
        self.assertEqual(self.sleep.await_args_list, [call(1.0), call(5.0), call(1.5)])
        self.assertEqual(len(client.requests), 4)
        self.assertTrue(
            all(request is trim_result.request for request in client.requests)
        )
        self.assertEqual(
            steps,
            [(kind, attempt) for attempt in range(1, 5) for kind in ("send", "closed")],
        )
        self.assertEqual(response.timing.ttft_seconds, 15.0)
        self.assertEqual(response.timing.total_seconds, 17.5)
        self.assert_final_log(
            captured,
            attempts=4,
            reason=ModelResponseEndReason.COMPLETED_NORMALLY,
            ttft_seconds=15.0,
            total_seconds=17.5,
        )
        self.assertIs(response.usage, self.usage)
        self.assertEqual(response.text, "answer")

    async def test_persistent_failure_stops_at_attempt_limit_including_initial_send(
        self,
    ):
        for limit in (1, 3):
            with self.subTest(limit=limit):
                self.sleep.reset_mock()
                failure = failed_event(ModelResponseEndReason.SERVICE_UNAVAILABLE)
                client, _ = self.scripted_client([[failure] for _ in range(limit + 1)])

                response, _ = await self.run_turn(
                    client, request_retry_config=RequestRetryConfig(max_attempts=limit)
                )

                self.assertEqual(len(client.requests), limit)
                self.assertEqual(self.sleep.await_count, limit - 1)
                self.assertEqual(response.reason, failure.reason)
                self.assertIs(response.error, failure.error)

    async def test_nonretryable_results_and_partial_text_never_wait_or_resend(self):
        cases = [
            ([self.completed], ModelResponseEndReason.COMPLETED_NORMALLY, ""),
            ([], ModelResponseEndReason.MISSING_END_EVENT, ""),
            (
                [RuntimeError("read failed")],
                ModelResponseEndReason.STREAM_READ_FAILED,
                "",
            ),
        ]
        for reason in (
            ModelResponseEndReason.AUTHENTICATION_FAILED,
            ModelResponseEndReason.PERMISSION_DENIED,
            ModelResponseEndReason.INVALID_REQUEST,
            ModelResponseEndReason.REQUEST_FAILED,
            ModelResponseEndReason.REQUEST_CANCELLED,
            ModelResponseEndReason.REQUEST_DEADLINE_EXCEEDED,
            ModelResponseEndReason.INSUFFICIENT_RETRY_TIME,
        ):
            cases.append(([failed_event(reason)], reason, ""))
        for detail in ("max_output_tokens", "content_filter"):
            terminal = EndEvent(
                ModelResponseEndReason.REQUEST_INCOMPLETE,
                None,
                ModelResponseIncompleteDetails(detail),
            )
            cases.append(([terminal], terminal.reason, ""))
        for text in ("partial", " ", "\n"):
            failure = failed_event(ModelResponseEndReason.READ_TIMEOUT)
            cases.append(([TextDeltaEvent(text), failure], failure.reason, text))

        for events, reason, text in cases:
            with self.subTest(events=events):
                self.sleep.reset_mock()
                self.uniform.reset_mock()
                self.displayed.clear()
                client, _ = self.scripted_client([events, [self.completed]])

                with self.assertLogs(
                    "llm_terminal_assistant.cli", level="INFO"
                ) as captured:
                    response, _ = await self.run_turn(client)

                self.assertEqual(self.wait_log_fields(captured), [])
                self.assertEqual(len(client.requests), 1)
                self.sleep.assert_not_called()
                self.uniform.assert_not_called()
                self.assertEqual(response.reason, reason)
                self.assertEqual(response.text, text)
                self.assertEqual("".join(self.displayed), text)

    async def test_shared_deadline_rejects_wait_that_would_use_remaining_budget(self):
        for deadline, expected in (
            (2.0, ModelResponseEndReason.REQUEST_DEADLINE_EXCEEDED),
            (6.0, ModelResponseEndReason.INSUFFICIENT_RETRY_TIME),
            (7.0, ModelResponseEndReason.INSUFFICIENT_RETRY_TIME),
        ):
            with self.subTest(deadline=deadline):
                self.now = 100.0
                self.sleep.reset_mock()
                client, steps = self.scripted_client(
                    [[failed_event(ModelResponseEndReason.RATE_LIMITED, 5.0)]],
                    close_seconds=2.0,
                )

                with self.assertLogs(
                    "llm_terminal_assistant.cli", level="INFO"
                ) as captured:
                    response, _ = await self.run_turn(
                        client,
                        request_timeout_config=RequestTimeoutConfig(
                            10, 30, 30, deadline
                        ),
                    )

                fields = self.attempt_log_fields(captured)
                self.assertEqual([entry["attempt"] for entry in fields], ["1", "1"])
                self.assertEqual(fields[-1]["reason"], "rate_limited")
                self.assertEqual(
                    self.wait_log_fields(captured),
                    [{**fields[-1], "planned_delay_seconds": 5.0}],
                )
                self.sleep.assert_not_called()
                self.assertEqual(len(client.requests), 1)
                self.assertEqual(steps, [("send", 1), ("closed", 1)])
                self.assertEqual(response.reason, expected)
                self.assertEqual(response.error.code, expected)
                self.assertIsNone(response.error.retry_after_seconds)
                self.assertEqual(response.timing.total_seconds, 2.0)
                self.assertIsNone(response.timing.ttft_seconds)
                self.assert_final_log(
                    captured,
                    attempts=1,
                    reason=expected,
                    ttft_seconds=None,
                    total_seconds=2.0,
                )

    async def test_deadline_is_checked_after_wait_before_another_send(self):
        async def overslept(delay):
            self.now = 110.0

        sleep = AsyncMock(side_effect=overslept)
        client, _ = self.scripted_client(
            [[failed_event(ModelResponseEndReason.RATE_LIMITED)]]
        )
        response, _ = await self.run_turn(
            client,
            sleep=sleep,
            request_timeout_config=RequestTimeoutConfig(10, 30, 30, 10),
        )

        sleep.assert_awaited_once_with(0.5)
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(
            response.reason, ModelResponseEndReason.REQUEST_DEADLINE_EXCEEDED
        )
        self.assertEqual(response.error.code, response.reason)
        self.assertEqual(response.timing.total_seconds, 10.0)

    async def test_deadline_interrupts_pending_retry_wait_and_returns_response(self):
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        pending = loop.create_future()
        real_timeout = asyncio.timeout
        timeouts = []

        def capture_timeout(seconds):
            context = real_timeout(seconds)
            timeouts.append(context)
            return context

        async def waiting(delay):
            started.set()
            await pending

        client, _ = self.scripted_client(
            [[failed_event(ModelResponseEndReason.RATE_LIMITED)]], close_seconds=2.0
        )
        with (
            patch(
                "llm_terminal_assistant.request_retry.asyncio.timeout",
                side_effect=capture_timeout,
            ) as timeout,
            self.assertLogs("llm_terminal_assistant.cli", level="INFO") as captured,
        ):
            task = asyncio.create_task(
                self.run_turn(
                    client,
                    sleep=waiting,
                    request_timeout_config=RequestTimeoutConfig(10, 30, 30, 10),
                ),
                name="test-stream-retry-deadline",
            )
            try:
                async with real_timeout(5):
                    await started.wait()
                    timeout.assert_called_once_with(8.0)
                    self.now = 110.0
                    timeouts[0].reschedule(loop.time() - 1.0)
                    response, _ = await task
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        self.assertTrue(pending.cancelled())
        self.assertTrue(timeouts[0].expired())
        self.assert_final_log(
            captured,
            attempts=1,
            reason=ModelResponseEndReason.REQUEST_DEADLINE_EXCEEDED,
            ttft_seconds=None,
            total_seconds=10.0,
        )
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(
            response.reason, ModelResponseEndReason.REQUEST_DEADLINE_EXCEEDED
        )
        self.assertEqual(response.error.code, response.reason)
        self.assertEqual(response.timing.total_seconds, 10.0)

    async def test_cancellation_during_retry_wait_returns_response_without_resending(
        self,
    ):
        started = asyncio.Event()
        pending = asyncio.get_running_loop().create_future()

        async def waiting(delay):
            started.set()
            await pending

        client, steps = self.scripted_client(
            [[failed_event(ModelResponseEndReason.RATE_LIMITED)]]
        )
        with self.assertLogs("llm_terminal_assistant.cli", level="INFO") as captured:
            task = asyncio.create_task(
                self.run_turn(client, sleep=waiting), name="test-stream-retry-cancel"
            )
            try:
                async with asyncio.timeout(5):
                    await started.wait()
                    self.assertEqual(steps, [("send", 1), ("closed", 1)])
                    self.now = 103.0
                    task.cancel()
                    response, _ = await task
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        self.assert_final_log(
            captured,
            attempts=1,
            reason=ModelResponseEndReason.REQUEST_CANCELLED,
            ttft_seconds=None,
            total_seconds=3.0,
        )
        self.assertFalse(task.cancelled())
        self.assertTrue(pending.cancelled())
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(response.reason, ModelResponseEndReason.REQUEST_CANCELLED)
        self.assertIsNone(response.error)
        self.assertIsNone(response.usage)
        self.assertIsNone(response.timing.ttft_seconds)
        self.assertEqual(response.timing.total_seconds, 3.0)

    async def test_cancellation_during_close_preserves_progress_and_waits_for_cleanup(
        self,
    ):
        for text in ("", "partial answer"):
            with self.subTest(text=text):
                await self.assert_close_cancellation(text)

    async def test_keyboard_cancellation_during_retry_wait_allows_next_question(self):
        for key in ("\x1b", "\x03"):
            with self.subTest(key=key):
                await self.assert_keyboard_cancellation(key)

    async def assert_keyboard_cancellation(self, key):
        config = replace(self.config, stream_output_enabled=True)
        client, steps = self.scripted_client(
            [
                [failed_event(ModelResponseEndReason.RATE_LIMITED)],
                [TextDeltaEvent("next answer"), self.completed],
            ]
        )
        started = asyncio.Event()
        pending_wait = asyncio.get_running_loop().create_future()
        responses = []
        output = StringIO()

        async def waiting(delay):
            started.set()
            await pending_wait

        async def observed_turn(*args, **kwargs):
            result = await send_stream_conversation_turn(
                *args, **kwargs, sleep=waiting, uniform=lambda low, high: 0.5
            )
            responses.append(result[0])
            return result

        with (
            create_pipe_input() as terminal_input,
            patch("llm_terminal_assistant.cli.PromptSession") as session,
            patch(
                "llm_terminal_assistant.cli.send_stream_conversation_turn",
                side_effect=observed_turn,
            ),
            self.assertLogs("llm_terminal_assistant.cli", level="INFO") as captured,
            redirect_stdout(output),
        ):
            session.return_value = SimpleNamespace(
                app=SimpleNamespace(input=terminal_input, ttimeoutlen=0),
                prompt_async=AsyncMock(side_effect=["first", "second", "exit"]),
            )
            task = asyncio.create_task(
                talk(client, config, self.budgeter), name="test-terminal-retry-cancel"
            )
            try:
                async with asyncio.timeout(5):
                    await started.wait()
                    self.assertEqual(steps, [("send", 1), ("closed", 1)])
                    terminal_input.send_text(key)
                    await task
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        self.assertTrue(pending_wait.cancelled())
        self.assertEqual(len(client.requests), 2)
        fields = self.attempt_log_fields(captured)
        self.assertEqual([entry["attempt"] for entry in fields], ["1"] * 4)
        first_id, second_id = fields[0]["request_id"], fields[2]["request_id"]
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(fields[1]["request_id"], first_id)
        self.assertEqual(fields[3]["request_id"], second_id)
        self.assertEqual(fields[1]["reason"], "rate_limited")
        self.assertEqual(fields[3]["reason"], "completed_normally")
        self.assertEqual(
            self.wait_log_fields(captured),
            [{**fields[1], "planned_delay_seconds": 0.5}],
        )
        self.assertEqual(client.requests[0].input[-1], Message("user", "first"))
        self.assertEqual(client.requests[1].input[-1], Message("user", "second"))
        self.assertEqual(
            [response.reason for response in responses],
            [
                ModelResponseEndReason.REQUEST_CANCELLED,
                ModelResponseEndReason.COMPLETED_NORMALLY,
            ],
        )
        self.assertIsNone(responses[0].error)
        self.assertEqual(output.getvalue().count("Request was cancelled."), 1)
        self.assertIn("next answer\nExiting...", output.getvalue())

    async def assert_close_cancellation(self, text):
        self.now = 100.0
        self.displayed.clear()
        self.sleep.reset_mock()
        started = asyncio.Event()
        pending_close = asyncio.get_running_loop().create_future()
        cleanup_tasks, steps = [], []
        client = FakeClient(self.config)

        async def stream(request):
            client.requests.append(request)
            try:
                self.now = 101.0
                yield TextDeltaEvent(text)
                yield UsageEvent(self.usage)
                yield failed_event(ModelResponseEndReason.RATE_LIMITED)
            finally:
                cleanup_tasks.append(asyncio.current_task())
                started.set()
                await pending_close
                self.now = 107.0
                steps.append("closed")

        with (
            patch.object(client, "send_stream", side_effect=stream),
            self.assertLogs("llm_terminal_assistant.cli", level="INFO") as captured,
        ):
            task = asyncio.create_task(
                self.run_turn(client), name="test-stream-close-cancel"
            )
            try:
                async with asyncio.timeout(5):
                    await started.wait()
                    self.now = 103.0
                    task.cancel()
                    # 让取消送达消费者，关闭任务仍由未完成的 Future 阻塞。
                    await asyncio.sleep(0)
                    self.assertFalse(task.done())
                    self.assertFalse(cleanup_tasks[0].done())
                    self.assertFalse(pending_close.cancelled())
                    self.assertEqual(len(self.attempt_log_fields(captured)), 1)
                    pending_close.set_result(None)
                    response, _ = await task
                    steps.append("returned")
            finally:
                if not pending_close.done():
                    pending_close.set_result(None)
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, *cleanup_tasks, return_exceptions=True)

        self.assertEqual(steps, ["closed", "returned"])
        fields = self.attempt_log_fields(captured)
        self.assertEqual([entry["attempt"] for entry in fields], ["1", "1"])
        self.assertEqual(fields[0]["request_id"], fields[1]["request_id"])
        self.assertEqual(fields[1]["reason"], "request_cancelled")
        self.assertTrue(
            all(task.done() and not task.cancelled() for task in cleanup_tasks)
        )
        self.assertEqual(len(client.requests), 1)
        self.sleep.assert_not_called()
        self.assertEqual(response.reason, ModelResponseEndReason.REQUEST_CANCELLED)
        self.assertIsNone(response.error)
        self.assertEqual(response.text, text)
        self.assertEqual("".join(self.displayed), text)
        self.assertIs(response.usage, self.usage)
        self.assertEqual(response.timing.ttft_seconds, 1.0 if text else None)
        self.assertEqual(response.timing.total_seconds, 7.0)
        self.assert_final_log(
            captured,
            attempts=1,
            reason=ModelResponseEndReason.REQUEST_CANCELLED,
            ttft_seconds=1.0 if text else None,
            total_seconds=7.0,
        )


if __name__ == "__main__":
    unittest.main()

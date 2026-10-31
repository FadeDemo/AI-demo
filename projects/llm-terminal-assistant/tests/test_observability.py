import asyncio
import json
import logging
import unittest
from contextlib import contextmanager
from io import StringIO
from threading import Event
from unittest.mock import Mock, patch

from llm_terminal_assistant.adapter.fake_client import FakeClient
from llm_terminal_assistant.adapter.fake_model import (
    CodePointTokenCounter,
    FakeModelRequestEncoder,
)
from llm_terminal_assistant.budgeter import Budgeter, BudgetRejectedError
from llm_terminal_assistant.cli import (
    send_conversation_turn,
    send_stream_conversation_turn,
)
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
    ModelResponse,
    ModelResponseEndReason,
    ModelResponseError,
    ModelUsage,
    OutputTokensDetails,
)
from llm_terminal_assistant.request_control import RequestStoppedError
from llm_terminal_assistant.stream.events import EndEvent, TextDeltaEvent, UsageEvent
from llm_terminal_assistant.tools.definition import RegisteredTool, ToolDefinition
from llm_terminal_assistant.tools.errors import ToolLoopStoppedError
from llm_terminal_assistant.tools.executor import ToolExecutor
from llm_terminal_assistant.tools.loop import ToolLoopLimits
from llm_terminal_assistant.tools.protocol import ToolCallRequest
from llm_terminal_assistant.tools.registry import ToolRegistry

AUTH = "FAKE_AUTH_KEY_TASK2_DO_NOT_LOG"
USER = "USER_CANARY sk-fake-input learner@example.invalid"
BODY = "MODEL_CANARY sk-fake-answer author@example.invalid"
TOOL_OUTPUT = "TOOL_CANARY sk-fake-tool reader@example.invalid"
UNKNOWN_TOOL = "UNKNOWN_CANARY_sk-fake-name_owner@example.invalid"
RAW_ERROR = "ERROR_CANARY sk-fake-error support@example.invalid"
CANARIES = (AUTH, USER, BODY, TOOL_OUTPUT, UNKNOWN_TOOL, RAW_ERROR)
CANARIES += tuple(part for value in CANARIES for part in value.split())
COMPLETED = ModelResponseEndReason.COMPLETED_NORMALLY


class CapturedLogs(logging.StreamHandler):
    def __init__(self):
        self.output = StringIO()
        super().__init__(self.output)
        self.records = []
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    def emit(self, record):
        self.records.append(record)
        super().emit(record)


@contextmanager
def capture_logs():
    logger = logging.getLogger("llm_terminal_assistant")
    handler = CapturedLogs()
    previous_level, previous_propagate = logger.level, logger.propagate
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
        handler.close()


def usage(input_tokens, output_tokens):
    return ModelUsage(
        input_tokens,
        InputTokensDetails(0, 0),
        output_tokens,
        OutputTokensDetails(0),
        input_tokens + output_tokens,
    )


class ObservabilityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = 100.0
        self.displayed = []
        self.config = ModelConfig(AUTH, "", "fake-model", FAKE_MODEL_PROFILE)
        self.budgeter = Budgeter(
            token_counter=CodePointTokenCounter(),
            request_encoder=FakeModelRequestEncoder(),
            model_limits=ModelLimits(context_window_tokens=100_000),
            safety_margin_tokens=0,
        )

    def options(self, client):
        return {
            "client": client,
            "budgeter": self.budgeter,
            "system_message": Message("system", "Follow the application task."),
            "completed_turns": [],
            "current_user_message": Message("user", USER),
            "reserved_output_tokens": 128,
            "min_reserved_recent_turns": 1,
            "clock": lambda: self.now,
        }

    async def sleep(self, seconds):
        self.now += seconds

    async def stream_turn(self, client, **overrides):
        options = {
            **self.options(client),
            "display_text": self.displayed.append,
            "request_retry_config": RequestRetryConfig(max_attempts=2),
            "sleep": self.sleep,
            "uniform": lambda low, high: high,
            **overrides,
        }
        return await send_stream_conversation_turn(**options)

    def stream_client(self, attempts):
        client = FakeClient(self.config)
        closed = []

        async def stream(request):
            index = len(client.requests)
            self.assertEqual(len(closed), index)
            client.requests.append(request)
            try:
                for event in attempts[index]:
                    self.now += 1.0
                    if isinstance(event, Exception):
                        raise event
                    yield event
            finally:
                self.now += 2.0
                closed.append(index)

        self.enterContext(patch.object(client, "send_stream", side_effect=stream))
        return client, closed

    def assert_summary(self, logs, *, calls, retries, reason, entry):
        summaries = [
            r for r in logs.records if getattr(r, "event", None) == "request_summary"
        ]
        self.assertEqual(len(summaries), 1)
        summary = summaries[0]
        self.assertIs(summary, logs.records[-1])
        self.assertEqual(logs.output.getvalue().count("Request finished:"), 1)
        self.assertRegex(summary.request_id, r"^[0-9a-f]{32}$")
        self.assertRegex(summary.prompt_version, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(summary.model, "fake-model")
        self.assertEqual(summary.entry, entry)
        self.assertEqual(summary.model_calls, calls)
        self.assertEqual(summary.retries, retries)
        self.assertEqual(summary.reason, reason)
        call_logs = [
            r for r in logs.records if getattr(r, "event", None) == "model_call"
        ]
        self.assertEqual(
            [r.model_call_index for r in call_logs], list(range(1, calls + 1))
        )
        for record in logs.records:
            if hasattr(record, "request_id"):
                self.assertEqual(record.request_id, summary.request_id)
            self.assertIsNone(record.exc_info)
        text = logs.output.getvalue()
        self.assertNotIn("Traceback", text)
        for canary in CANARIES:
            self.assertNotIn(canary, text)
        return summary, call_logs

    def assert_credentials_absent(self, client):
        self.assertEqual(client.api_key, AUTH)
        self.assertTrue(client.requests)
        for request in client.requests:
            self.assertNotIn(AUTH, repr(request.input))

    async def test_normal_stream_and_zero_or_missing_usage_are_distinct(self):
        for reported_usage, expected_tokens, complete in (
            (usage(20, 5), 25, True),
            (usage(0, 0), 0, True),
            (None, None, False),
        ):
            with self.subTest(usage=reported_usage):
                self.now = 100.0
                events = [TextDeltaEvent(""), TextDeltaEvent(BODY)]
                if reported_usage is not None:
                    events.append(UsageEvent(reported_usage))
                events.append(EndEvent(COMPLETED, None, None))
                client, closed = self.stream_client([events])
                encoder = self.budgeter.request_encoder
                original_encode = encoder.encode_request

                def prepare(request, original_encode=original_encode):
                    self.now += 3.0
                    return original_encode(request)

                with (
                    capture_logs() as logs,
                    patch.object(encoder, "encode_request", side_effect=prepare),
                ):
                    response, _ = await self.stream_turn(client)
                summary, calls = self.assert_summary(
                    logs, calls=1, retries=0, reason=COMPLETED, entry="stream"
                )
                self.assertEqual(response.text, BODY)
                self.assertEqual(summary.status, "success")
                self.assertEqual(summary.ttft_status, "observed")
                self.assertEqual(summary.ttft_seconds, 5.0)
                self.assertEqual(summary.total_seconds, 3.0 + len(events) + 2.0)
                self.assertEqual(summary.total_tokens, expected_tokens)
                self.assertEqual(summary.usage_complete, complete)
                self.assertEqual(summary.unknown_usage_calls, int(not complete))
                self.assertEqual(calls[0].total_tokens, expected_tokens)
                self.assertEqual(closed, [0])
                self.assertIn(BODY, self.displayed)
                self.assert_credentials_absent(client)

    async def test_retry_keeps_failed_call_usage_and_aggregates_each_call_once(self):
        for failed_usage in (None, usage(3, 1)):
            with self.subTest(failed_usage=failed_usage):
                self.now = 100.0
                failed = [] if failed_usage is None else [UsageEvent(failed_usage)]
                failed.append(
                    EndEvent(
                        ModelResponseEndReason.RATE_LIMITED,
                        ModelResponseError(RAW_ERROR, RAW_ERROR),
                        None,
                    )
                )
                client, closed = self.stream_client(
                    [
                        failed,
                        [
                            TextDeltaEvent(BODY),
                            UsageEvent(usage(20, 5)),
                            EndEvent(COMPLETED, None, None),
                        ],
                    ]
                )
                with capture_logs() as logs:
                    response, _ = await self.stream_turn(client)
                summary, calls = self.assert_summary(
                    logs, calls=2, retries=1, reason=COMPLETED, entry="stream"
                )
                self.assertEqual(summary.total_tokens, 25 + (4 if failed_usage else 0))
                self.assertEqual(summary.input_tokens, 20 + (3 if failed_usage else 0))
                self.assertEqual(summary.output_tokens, 5 + (1 if failed_usage else 0))
                self.assertEqual(summary.usage_complete, failed_usage is not None)
                self.assertEqual(summary.unknown_usage_calls, int(failed_usage is None))
                self.assertEqual(calls[0].reason, "rate_limited")
                self.assertEqual(calls[0].total_tokens, 4 if failed_usage else None)
                self.assertEqual(calls[1].attempt, 2)
                self.assertEqual(summary.ttft_seconds, len(failed) + 4.0)
                self.assertEqual(summary.total_seconds, len(failed) + 8.0)
                self.assertEqual(response.usage.total_tokens, 25)
                self.assertEqual(closed, [0, 1])
                self.assertIs(client.requests[0], client.requests[1])
                self.assert_credentials_absent(client)

    async def test_timeout_and_cancellation_summarize_after_stream_cleanup(self):
        for stop in ("timeout", "cancel"):
            with self.subTest(stop=stop):
                await self.assert_stream_stop(stop)

    async def assert_stream_stop(self, stop):
        self.now = 100.0
        client = FakeClient(self.config)
        scopes, closed = [], []
        waiting = asyncio.Event()
        loop = asyncio.get_running_loop()

        def record_timeout(seconds):
            scope = asyncio.timeout(seconds)
            scopes.append(scope)
            return scope

        async def stream(request):
            client.requests.append(request)
            try:
                self.now += 3.0
                waiting.set()
                if stop == "timeout":
                    loop.call_soon(scopes[-1].reschedule, loop.time())
                await asyncio.Event().wait()
                yield TextDeltaEvent(BODY)
            finally:
                self.now += 2.0
                closed.append(True)

        with (
            capture_logs() as logs,
            patch.object(client, "send_stream", side_effect=stream),
            patch(
                "llm_terminal_assistant.stream.consumer.timeout",
                side_effect=record_timeout,
            ),
        ):
            task = asyncio.create_task(
                self.stream_turn(
                    client,
                    request_retry_config=RequestRetryConfig(max_attempts=1),
                    request_timeout_config=RequestTimeoutConfig(10, 30, 30, 120),
                )
            )
            try:
                async with asyncio.timeout(2):
                    await waiting.wait()
                    if stop == "cancel":
                        task.cancel()
                    response, _ = await task
            finally:
                if not task.done():
                    task.cancel()
                    await task
        reason = "first_event_timeout" if stop == "timeout" else "request_cancelled"
        summary, calls = self.assert_summary(
            logs, calls=1, retries=0, reason=reason, entry="stream"
        )
        self.assertEqual(response.reason, reason)
        self.assertEqual(calls[0].reason, reason)
        self.assertEqual(summary.ttft_status, "missing")
        self.assertIsNone(summary.ttft_seconds)
        self.assertIsNone(summary.total_tokens)
        self.assertFalse(summary.usage_complete)
        self.assertEqual(summary.total_seconds, 5.0)
        self.assertEqual(closed, [True])
        self.assert_credentials_absent(client)

    async def test_new_turn_changes_id_and_prompt_version_follows_only_instructions(
        self,
    ):
        summaries = []
        for prompt, user in (
            ("Task v1", USER),
            ("Task v1", "another question"),
            ("Task v2", USER),
        ):
            client, _ = self.stream_client([[EndEvent(COMPLETED, None, None)]])
            with capture_logs() as logs:
                await self.stream_turn(
                    client,
                    system_message=Message("system", prompt),
                    current_user_message=Message("user", user),
                )
            summary, _ = self.assert_summary(
                logs, calls=1, retries=0, reason=COMPLETED, entry="stream"
            )
            summaries.append(summary)
        self.assertEqual(len({s.request_id for s in summaries}), 3)
        self.assertEqual(summaries[0].prompt_version, summaries[1].prompt_version)
        self.assertNotEqual(summaries[1].prompt_version, summaries[2].prompt_version)

    def test_tool_success_refusals_and_failure_keep_only_diagnostic_fields(self):
        handler = Mock(return_value={"text": TOOL_OUTPUT})
        failing_handler = Mock(side_effect=RuntimeError(RAW_ERROR))
        schema = {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        }
        definitions = [
            ToolDefinition("read_untrusted", "Read fixed text.", schema),
            ToolDefinition("failing_tool", "Fail safely.", schema),
        ]
        registry = ToolRegistry(
            [
                RegisteredTool(definitions[0], handler),
                RegisteredTool(definitions[1], failing_handler),
            ]
        )
        executor = ToolExecutor(registry)
        arguments = json.dumps({"text": USER})
        client = FakeClient(
            self.config,
            scripted_responses=[
                ModelResponse(
                    BODY,
                    COMPLETED,
                    usage(0, 0),
                    tool_calls=[
                        ToolCallRequest("read-1", "read_untrusted", arguments),
                        ToolCallRequest("bad-json", UNKNOWN_TOOL, RAW_ERROR),
                        ToolCallRequest("unknown-1", UNKNOWN_TOOL, arguments),
                        ToolCallRequest(
                            "bad-schema", "read_untrusted", json.dumps({"extra": USER})
                        ),
                        ToolCallRequest("failed-1", "failing_tool", arguments),
                    ],
                ),
                ModelResponse(BODY, COMPLETED, usage(20, 5)),
            ],
        )
        original_send = client.send

        def send(request):
            self.now += 2.0
            return original_send(request)

        with (
            capture_logs() as logs,
            patch.object(client, "send", side_effect=send),
            patch.object(registry, "get_tool", wraps=registry.get_tool) as lookup,
        ):
            response, _ = send_conversation_turn(
                **self.options(client), tools=definitions, executor=executor
            )
        summary, _ = self.assert_summary(
            logs, calls=2, retries=0, reason=COMPLETED, entry="tools"
        )
        self.assertIsNone(response.timing)
        self.assertEqual(summary.ttft_status, "not_applicable")
        self.assertIsNone(summary.ttft_seconds)
        self.assertEqual(summary.total_seconds, 4.0)
        self.assertEqual(summary.total_tokens, 25)
        self.assertTrue(summary.usage_complete)
        results = [
            r for r in logs.records if getattr(r, "event", None) == "tool_result"
        ]
        self.assertEqual(
            [r.tool_call_id for r in results],
            ["read-1", "bad-json", "unknown-1", "bad-schema", "failed-1"],
        )
        self.assertEqual(
            [r.tool_name for r in results],
            [
                "read_untrusted",
                "unregistered",
                "unregistered",
                "read_untrusted",
                "failing_tool",
            ],
        )
        self.assertEqual(
            [r.status for r in results],
            ["success", "rejected", "rejected", "rejected", "failed"],
        )
        self.assertEqual(
            [r.levelno for r in results],
            [
                logging.INFO,
                logging.WARNING,
                logging.WARNING,
                logging.WARNING,
                logging.ERROR,
            ],
        )
        self.assertEqual(
            [r.category for r in results],
            [
                None,
                "invalid_arguments",
                "unknown_tool",
                "invalid_arguments",
                "execution_failed",
            ],
        )
        self.assertIn(unittest.mock.call(UNKNOWN_TOOL), lookup.call_args_list)
        handler.assert_called_once_with({"text": USER})
        failing_handler.assert_called_once_with({"text": USER})
        self.assertIn(TOOL_OUTPUT, repr(client.requests[-1].input))
        self.assert_credentials_absent(client)

    def test_stopped_or_raised_complete_response_request_still_has_one_summary(self):
        for outcome in ("sdk_error", "cancel", "budget", "loop_limit"):
            with self.subTest(outcome=outcome):
                client = FakeClient(self.config)
                overrides = {}
                if outcome == "sdk_error":
                    error = RuntimeError(RAW_ERROR)
                    self.enterContext(patch.object(client, "send", side_effect=error))
                    exception_type, reason, calls = RuntimeError, "model_call_failed", 1
                elif outcome == "cancel":
                    cancelled = Event()
                    cancelled.set()
                    overrides["cancel_event"] = cancelled
                    exception_type, reason, calls = (
                        RequestStoppedError,
                        "request_cancelled",
                        0,
                    )
                elif outcome == "budget":
                    overrides["reserved_output_tokens"] = 100_000
                    exception_type, reason, calls = (
                        BudgetRejectedError,
                        "context_window_exceeded",
                        0,
                    )
                else:
                    client = FakeClient(
                        self.config,
                        scripted_responses=[
                            ModelResponse(
                                BODY,
                                COMPLETED,
                                usage(1, 1),
                                tool_calls=[ToolCallRequest("blocked-1", "read", "{}")],
                            )
                        ],
                    )
                    overrides.update(
                        executor=Mock(),
                        tool_loop_limits=ToolLoopLimits(max_tool_rounds=0),
                    )
                    exception_type, reason, calls = (
                        ToolLoopStoppedError,
                        "max_tool_rounds_reached",
                        1,
                    )
                with (
                    capture_logs() as logs,
                    self.assertRaises(exception_type) as caught,
                ):
                    send_conversation_turn(**{**self.options(client), **overrides})
                summary, _ = self.assert_summary(
                    logs, calls=calls, retries=0, reason=reason, entry="tools"
                )
                self.assertEqual(
                    summary.status, "cancelled" if outcome == "cancel" else "failed"
                )
                if outcome == "sdk_error":
                    self.assertIs(caught.exception, error)
                    self.assertIsNone(summary.total_tokens)
                elif calls == 0:
                    self.assertEqual(client.requests, [])
                    self.assertEqual(summary.total_tokens, 0)


if __name__ == "__main__":
    unittest.main()

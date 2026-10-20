import asyncio
import unittest
from functools import partial
from unittest.mock import patch

from llm_terminal_assistant.adapter.fake_client import FakeClient
from llm_terminal_assistant.config import ModelConfig, RequestTimeoutConfig
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import (
    FAKE_MODEL_PROFILE,
    InputTokensDetails,
    ModelRequest,
    ModelResponseEndReason,
    ModelResponseError,
    ModelResponseIncompleteDetails,
    ModelUsage,
    OutputTokensDetails,
)
from llm_terminal_assistant.stream.consumer import consume_stream
from llm_terminal_assistant.stream.events import EndEvent, TextDeltaEvent, UsageEvent


async def recording_stream(events, reads, closures):
    try:
        for event in events:
            reads.append(event)
            yield event
    finally:
        closures.append(True)


class StreamConsumerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.consume_stream = partial(consume_stream, start_at=10.0, clock=lambda: 12.0)
        self.usage = ModelUsage(
            input_tokens=23,
            input_tokens_details=InputTokensDetails(
                cached_tokens=7, cache_write_tokens=2
            ),
            output_tokens=11,
            output_tokens_details=OutputTokensDetails(reasoning_tokens=3),
            total_tokens=34,
        )
        self.completed = EndEvent(
            reason=ModelResponseEndReason.COMPLETED_NORMALLY,
            error=None,
            incomplete_details=None,
        )

    async def test_first_event_switches_to_idle_timeout_without_requiring_nonempty_text(
        self,
    ):
        config = RequestTimeoutConfig(10.0, 3.5, 30.0, 120.0)
        for first_event in (
            TextDeltaEvent("answer"),
            TextDeltaEvent(""),
            UsageEvent(self.usage),
            self.completed,
        ):
            with self.subTest(first_event=first_event):
                reads, closures, displayed = [], [], []

                async def delayed_stream(first_event, reads, closures):
                    try:
                        for event in (
                            first_event,
                            self.completed,
                            TextDeltaEvent("must not read"),
                        ):
                            reads.append(event)
                            yield event
                            await asyncio.sleep(0)
                    finally:
                        closures.append(True)

                # 首事件立即到达；后续让出执行机会，验证首事件计时已解除。
                with patch(
                    "llm_terminal_assistant.stream.consumer.timeout",
                    side_effect=lambda seconds: asyncio.timeout(
                        0 if seconds == config.first_event_seconds else seconds
                    ),
                ) as timeout:
                    response = await self.consume_stream(
                        delayed_stream(first_event, reads, closures),
                        displayed.append,
                        request_timeout_config=config,
                    )

                expected_timeouts = [config.first_event_seconds]
                if first_event is not self.completed:
                    expected_timeouts.append(config.stream_idle_seconds)
                self.assertEqual(
                    [call.args[0] for call in timeout.call_args_list],
                    expected_timeouts,
                )
                expected_text = (
                    first_event.delta if isinstance(first_event, TextDeltaEvent) else ""
                )
                self.assertEqual(
                    response.reason, ModelResponseEndReason.COMPLETED_NORMALLY
                )
                self.assertEqual(response.text, expected_text)
                self.assertEqual("".join(displayed), expected_text)
                self.assertEqual(
                    response.timing.ttft_seconds, 2.0 if expected_text else None
                )
                self.assertIs(
                    response.usage,
                    self.usage if isinstance(first_event, UsageEvent) else None,
                )
                self.assertIsNone(response.error)
                self.assertEqual(
                    reads,
                    [first_event]
                    if first_event is self.completed
                    else [first_event, self.completed],
                )
                self.assertEqual(closures, [True])

    async def test_idle_budget_starts_at_receipt_and_resets_for_each_event(self):
        config = RequestTimeoutConfig(10.0, 30.0, 5.0, 120.0)
        now = [10.0]
        reads, closures, displayed = [], [], []
        events = [
            (11.0, TextDeltaEvent("")),
            (15.0, UsageEvent(self.usage)),
            (19.0, TextDeltaEvent("first")),
            (23.0, TextDeltaEvent("second")),
            (27.0, self.completed),
        ]

        async def timed_stream():
            try:
                for received_at, event in events:
                    now[0] = received_at
                    reads.append(event)
                    yield event
            finally:
                closures.append(True)

        def display(delta):
            displayed.append(delta)
            now[0] += 2.0

        with patch(
            "llm_terminal_assistant.stream.consumer.timeout",
            wraps=asyncio.timeout,
        ) as timeout:
            response = await consume_stream(
                timed_stream(),
                display,
                start_at=10.0,
                clock=lambda: now[0],
                request_timeout_config=config,
            )

        # 展示消耗的时间计入空闲预算；空文本、用量和正文均刷新期限。
        self.assertEqual(
            [call.args[0] for call in timeout.call_args_list],
            [30.0, 3.0, 5.0, 3.0, 3.0],
        )
        self.assertEqual(response.reason, ModelResponseEndReason.COMPLETED_NORMALLY)
        self.assertIsNone(response.error)
        self.assertEqual(response.text, "firstsecond")
        self.assertEqual(displayed, ["", "first", "second"])
        self.assertIs(response.usage, self.usage)
        self.assertEqual(response.timing.ttft_seconds, 9.0)
        self.assertEqual(response.timing.total_seconds, 17.0)
        self.assertEqual(reads, [event for _, event in events])
        self.assertEqual(closures, [True])

    async def test_expired_idle_budget_stops_before_reading_an_immediate_event(self):
        config = RequestTimeoutConfig(10.0, 30.0, 5.0, 120.0)
        for display_seconds in (5.0, 6.0):
            with self.subTest(display_seconds=display_seconds):
                now = [10.0]
                reads, closures, displayed = [], [], []
                first = TextDeltaEvent("partial")

                def display(
                    delta, displayed=displayed, now=now, display_seconds=display_seconds
                ):
                    displayed.append(delta)
                    now[0] += display_seconds

                with patch(
                    "llm_terminal_assistant.stream.consumer.timeout",
                    wraps=asyncio.timeout,
                ) as timeout:
                    response = await consume_stream(
                        recording_stream(
                            [first, TextDeltaEvent("must not read"), self.completed],
                            reads,
                            closures,
                        ),
                        display,
                        start_at=10.0,
                        clock=lambda now=now: now[0],
                        request_timeout_config=config,
                    )

                timeout.assert_called_once_with(config.first_event_seconds)
                self.assertEqual(
                    response.reason, ModelResponseEndReason.STREAM_IDLE_TIMEOUT
                )
                self.assertEqual(response.error.code, "stream_idle_timeout")
                self.assertEqual(response.text, "partial")
                self.assertEqual(displayed, ["partial"])
                self.assertEqual(response.timing.ttft_seconds, 0.0)
                self.assertEqual(response.timing.total_seconds, display_seconds)
                self.assertEqual(reads, [first])
                self.assertEqual(closures, [True])

    async def test_zero_ttft_is_preserved_and_measured_before_display(self):
        now = [10.0]
        reads, closures, displayed = [], [], []

        def display(delta):
            displayed.append(delta)
            now[0] += 2.0

        result = await consume_stream(
            recording_stream(
                [TextDeltaEvent("first"), TextDeltaEvent("second"), self.completed],
                reads,
                closures,
            ),
            display,
            start_at=10.0,
            clock=lambda: now[0],
        )

        self.assertEqual(result.timing.ttft_seconds, 0.0)
        self.assertEqual(result.timing.total_seconds, 4.0)
        self.assertEqual(displayed, ["first", "second"])
        self.assertEqual(closures, [True])

    async def test_displays_fake_stream_incrementally_and_returns_assembled_response(
        self,
    ):
        client = FakeClient(
            ModelConfig(
                api_key="",
                base_url="",
                model="fake-model",
                model_profile=FAKE_MODEL_PROFILE,
            ),
            scripted_events=[
                TextDeltaEvent(delta=""),
                UsageEvent(usage=self.usage),
                TextDeltaEvent(delta="first "),
                TextDeltaEvent(delta="second\n"),
                TextDeltaEvent(delta="third"),
                self.completed,
            ],
        )
        request = ModelRequest(
            input=[Message(role="user", content="question")],
            reserved_output_tokens=128,
        )
        displayed = []
        expected_display = []
        upstream = client.send_stream(request)

        async def observed_stream():
            try:
                async for event in upstream:
                    if isinstance(event, TextDeltaEvent):
                        expected_display.append(event.delta)
                    yield event
                    self.assertEqual(displayed, expected_display)
            finally:
                await upstream.aclose()

        result = await self.consume_stream(observed_stream(), displayed.append)

        self.assertEqual(displayed, ["", "first ", "second\n", "third"])
        self.assertEqual(result.text, "first second\nthird")
        self.assertEqual(result.reason, ModelResponseEndReason.COMPLETED_NORMALLY)
        self.assertIs(result.usage, self.usage)
        self.assertIsNone(result.error)
        self.assertIsNone(result.incomplete_details)
        self.assertEqual(client.requests, [request])

    async def test_stops_at_terminal_event_and_closes_without_reading_tail(self):
        events = [
            TextDeltaEvent(delta="answer"),
            self.completed,
            TextDeltaEvent(delta="must not display"),
            EndEvent(
                reason=ModelResponseEndReason.REQUEST_FAILED,
                error=ModelResponseError(code="server_error", message="late error"),
                incomplete_details=None,
            ),
        ]
        reads, closures, displayed = [], [], []

        result = await self.consume_stream(
            recording_stream(events, reads, closures), displayed.append
        )

        self.assertEqual(reads, events[:2])
        self.assertEqual(displayed, ["answer"])
        self.assertEqual(result.text, "answer")
        self.assertEqual(result.reason, ModelResponseEndReason.COMPLETED_NORMALLY)
        self.assertIsNone(result.usage)
        self.assertIsNone(result.error)
        self.assertEqual(closures, [True])

    async def test_preserves_failed_and_truncated_terminal_details_without_usage(self):
        terminals = [
            EndEvent(
                reason=ModelResponseEndReason.REQUEST_FAILED,
                error=ModelResponseError(
                    code="server_error", message="Generation failed."
                ),
                incomplete_details=None,
            ),
            EndEvent(
                reason=ModelResponseEndReason.REQUEST_INCOMPLETE,
                error=None,
                incomplete_details=ModelResponseIncompleteDetails(
                    reason="max_output_tokens"
                ),
            ),
        ]
        for terminal in terminals:
            with self.subTest(reason=terminal.reason):
                events = [TextDeltaEvent(delta="partial"), terminal]
                reads, closures, displayed = [], [], []

                result = await self.consume_stream(
                    recording_stream(events, reads, closures), displayed.append
                )

                self.assertEqual(displayed, ["partial"])
                self.assertEqual(result.text, "partial")
                self.assertEqual(result.reason, terminal.reason)
                self.assertEqual(result.error, terminal.error)
                self.assertEqual(result.incomplete_details, terminal.incomplete_details)
                self.assertIsNone(result.usage)
                self.assertEqual(closures, [True])

    async def test_missing_terminal_preserves_available_text_and_usage_and_closes(self):
        cases = [
            ([], "", None),
            ([TextDeltaEvent(delta="partial")], "partial", None),
            ([UsageEvent(usage=self.usage)], "", self.usage),
            (
                [TextDeltaEvent(delta="partial"), UsageEvent(usage=self.usage)],
                "partial",
                self.usage,
            ),
        ]
        for events, text, usage in cases:
            with self.subTest(events=events):
                reads, closures, displayed = [], [], []

                result = await self.consume_stream(
                    recording_stream(events, reads, closures), displayed.append
                )

                self.assertEqual(
                    result.reason, ModelResponseEndReason.MISSING_END_EVENT
                )
                self.assertEqual(result.text, text)
                self.assertEqual("".join(displayed), text)
                self.assertIs(result.usage, usage)
                self.assertIsNone(result.error)
                self.assertIsNone(result.incomplete_details)
                self.assertEqual(reads, events)
                self.assertEqual(closures, [True])

    async def test_read_exception_returns_failure_preserves_progress_and_closes(self):
        cases = [
            ([], "", None),
            ([TextDeltaEvent(delta="partial")], "partial", None),
            (
                [TextDeltaEvent(delta="partial"), UsageEvent(usage=self.usage)],
                "partial",
                self.usage,
            ),
        ]
        for events, text, usage in cases:
            with self.subTest(events=events):
                closures, displayed = [], []

                async def failing_stream(events, closures):
                    try:
                        for event in events:
                            yield event
                        raise RuntimeError("private upstream error details")
                    finally:
                        closures.append(True)

                result = await self.consume_stream(
                    failing_stream(events, closures), displayed.append
                )

                self.assertEqual(
                    result.reason, ModelResponseEndReason.STREAM_READ_FAILED
                )
                self.assertEqual(result.text, text)
                self.assertEqual("".join(displayed), text)
                self.assertIs(result.usage, usage)
                self.assertEqual(result.error.code, "stream_read_failed")
                self.assertIn("incomplete", result.error.message)
                self.assertNotIn("private upstream error details", result.error.message)
                self.assertIsNone(result.incomplete_details)
                self.assertEqual(closures, [True])

    async def test_keyboard_interrupt_propagates_and_closes(self):
        closures = []

        async def interrupted_stream():
            try:
                yield TextDeltaEvent(delta="partial")
                raise KeyboardInterrupt
            finally:
                closures.append(True)

        displayed = []
        with self.assertRaises(KeyboardInterrupt):
            await self.consume_stream(interrupted_stream(), displayed.append)

        self.assertEqual(displayed, ["partial"])
        self.assertEqual(closures, [True])

    async def test_display_exception_propagates_and_closes_without_reading_more(self):
        failure = RuntimeError("display failed")
        events = [TextDeltaEvent(delta="partial"), self.completed]
        reads, closures = [], []

        def failing_display(delta):
            raise failure

        with self.assertRaises(RuntimeError) as caught:
            await self.consume_stream(
                recording_stream(events, reads, closures), failing_display
            )

        self.assertIs(caught.exception, failure)
        self.assertEqual(reads, events[:1])
        self.assertEqual(closures, [True])


if __name__ == "__main__":
    unittest.main()

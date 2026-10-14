import unittest

from llm_terminal_assistant.adapter.fake_client import FakeClient
from llm_terminal_assistant.config import ModelConfig
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


def recording_stream(events, reads, closures):
    try:
        for event in events:
            reads.append(event)
            yield event
    finally:
        closures.append(True)


class StreamConsumerTests(unittest.TestCase):
    def setUp(self):
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

    def test_displays_fake_stream_incrementally_and_returns_assembled_response(self):
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

        def observed_stream():
            try:
                for event in upstream:
                    if isinstance(event, TextDeltaEvent):
                        expected_display.append(event.delta)
                    yield event
                    self.assertEqual(displayed, expected_display)
            finally:
                upstream.close()

        result = consume_stream(observed_stream(), displayed.append)

        self.assertEqual(displayed, ["", "first ", "second\n", "third"])
        self.assertEqual(result.text, "first second\nthird")
        self.assertEqual(result.reason, ModelResponseEndReason.COMPLETED_NORMALLY)
        self.assertIs(result.usage, self.usage)
        self.assertIsNone(result.error)
        self.assertIsNone(result.incomplete_details)
        self.assertEqual(client.requests, [request])

    def test_stops_at_terminal_event_and_closes_without_reading_tail(self):
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

        result = consume_stream(
            recording_stream(events, reads, closures), displayed.append
        )

        self.assertEqual(reads, events[:2])
        self.assertEqual(displayed, ["answer"])
        self.assertEqual(result.text, "answer")
        self.assertEqual(result.reason, ModelResponseEndReason.COMPLETED_NORMALLY)
        self.assertIsNone(result.usage)
        self.assertIsNone(result.error)
        self.assertEqual(closures, [True])

    def test_preserves_failed_and_truncated_terminal_details_without_usage(self):
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

                result = consume_stream(
                    recording_stream(events, reads, closures), displayed.append
                )

                self.assertEqual(displayed, ["partial"])
                self.assertEqual(result.text, "partial")
                self.assertEqual(result.reason, terminal.reason)
                self.assertEqual(result.error, terminal.error)
                self.assertEqual(result.incomplete_details, terminal.incomplete_details)
                self.assertIsNone(result.usage)
                self.assertEqual(closures, [True])

    def test_missing_terminal_preserves_available_text_and_usage_and_closes(self):
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

                result = consume_stream(
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

    def test_read_exception_propagates_after_display_and_closes(self):
        failure = RuntimeError("read failed")
        closures, displayed = [], []

        def failing_stream():
            try:
                yield TextDeltaEvent(delta="partial")
                raise failure
            finally:
                closures.append(True)

        with self.assertRaises(RuntimeError) as caught:
            consume_stream(failing_stream(), displayed.append)

        self.assertIs(caught.exception, failure)
        self.assertEqual(displayed, ["partial"])
        self.assertEqual(closures, [True])

    def test_display_exception_propagates_and_closes_without_reading_more(self):
        failure = RuntimeError("display failed")
        events = [TextDeltaEvent(delta="partial"), self.completed]
        reads, closures = [], []

        def failing_display(delta):
            raise failure

        with self.assertRaises(RuntimeError) as caught:
            consume_stream(recording_stream(events, reads, closures), failing_display)

        self.assertIs(caught.exception, failure)
        self.assertEqual(reads, events[:1])
        self.assertEqual(closures, [True])


if __name__ == "__main__":
    unittest.main()

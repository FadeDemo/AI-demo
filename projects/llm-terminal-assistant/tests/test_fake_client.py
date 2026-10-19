import unittest
from contextlib import redirect_stdout
from io import StringIO

from llm_terminal_assistant.adapter.fake_client import FakeClient
from llm_terminal_assistant.cli import output_model_response
from llm_terminal_assistant.config import ModelConfig
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import (
    FAKE_MODEL_PROFILE,
    InputTokensDetails,
    ModelRequest,
    ModelResponse,
    ModelResponseEndReason,
    ModelUsage,
    OutputTokensDetails,
)
from llm_terminal_assistant.stream.events import EndEvent, TextDeltaEvent, UsageEvent


def build_config() -> ModelConfig:
    return ModelConfig(
        api_key="",
        base_url="",
        model="fake-model",
        model_profile=FAKE_MODEL_PROFILE,
        provider="faked",
    )


def build_request() -> ModelRequest:
    return ModelRequest(
        input=[Message(role="user", content="test prompt")],
        reserved_output_tokens=128,
    )


def build_response(text: str) -> ModelResponse:
    return ModelResponse(
        text=text,
        reason=ModelResponseEndReason.COMPLETED_NORMALLY,
        usage=ModelUsage(
            input_tokens=0,
            input_tokens_details=InputTokensDetails(
                cached_tokens=0,
                cache_write_tokens=0,
            ),
            output_tokens=0,
            output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
            total_tokens=0,
        ),
    )


def capture_output(response: ModelResponse) -> str:
    output = StringIO()
    with redirect_stdout(output):
        output_model_response(response)
    return output.getvalue()


class FakeClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_streams_scripted_events_in_order_without_default_fallback(self):
        request = build_request()
        scripted_events = [
            TextDeltaEvent(delta="first"),
            TextDeltaEvent(delta="second"),
            TextDeltaEvent(delta="third"),
            UsageEvent(usage=build_response("").usage),
            EndEvent(
                reason=ModelResponseEndReason.COMPLETED_NORMALLY,
                error=None,
                incomplete_details=None,
            ),
        ]
        expected_events = tuple(scripted_events)
        client = FakeClient(build_config(), scripted_events=scripted_events)

        stream = client.send_stream(request)

        self.assertEqual(client.requests, [])
        for expected_event in expected_events:
            self.assertIs(await anext(stream), expected_event)
            self.assertEqual(client.requests, [request])
        with self.assertRaises(StopAsyncIteration):
            await anext(stream)
        self.assertEqual(scripted_events, list(expected_events))
        self.assertEqual([event async for event in client.send_stream(request)], [])
        self.assertEqual(client.requests, [request, request])

    async def test_preserves_empty_and_unterminated_scripted_streams(self):
        for scripted_events in ([], [TextDeltaEvent(delta="partial answer")]):
            with self.subTest(scripted_events=scripted_events):
                request = build_request()
                client = FakeClient(build_config(), scripted_events=scripted_events)

                events = [event async for event in client.send_stream(request)]

                self.assertEqual(events, scripted_events)
                self.assertEqual(client.requests, [request])

    async def test_default_normal_stream_matches_response_on_repeated_calls(self):
        first_request = build_request()
        second_request = ModelRequest(
            input=[Message(role="user", content="second prompt")],
            reserved_output_tokens=128,
        )
        expected_response = FakeClient(build_config()).send(first_request)
        client = FakeClient(build_config())

        for request in (first_request, second_request):
            events = [event async for event in client.send_stream(request)]

            self.assertGreaterEqual(len(events), 3)
            self.assertTrue(
                all(isinstance(event, TextDeltaEvent) for event in events[:-2])
            )
            self.assertEqual(
                "".join(event.delta for event in events[:-2]), expected_response.text
            )
            self.assertIsInstance(events[-2], UsageEvent)
            self.assertEqual(events[-2].usage, expected_response.usage)
            self.assertEqual(
                events[-1],
                EndEvent(
                    reason=expected_response.reason,
                    error=expected_response.error,
                    incomplete_details=expected_response.incomplete_details,
                ),
            )
        self.assertEqual(client.requests, [first_request, second_request])

    async def test_default_truncated_stream_reports_output_limit(self):
        request = build_request()
        client = FakeClient(build_config(), outcome="max_output_tokens")

        events = [event async for event in client.send_stream(request)]

        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], EndEvent)
        self.assertEqual(events[0].reason, ModelResponseEndReason.REQUEST_INCOMPLETE)
        self.assertIsNone(events[0].error)
        self.assertEqual(events[0].incomplete_details.reason, "max_output_tokens")
        self.assertEqual(client.requests, [request])

    def test_returns_scripted_responses_and_records_requests_in_order(self):
        first_response = build_response("first response")
        second_response = build_response("second response")
        first_request = build_request()
        second_request = ModelRequest(
            input=[Message(role="user", content="second prompt")],
            reserved_output_tokens=128,
        )
        client = FakeClient(
            build_config(),
            scripted_responses=[first_response, second_response],
        )

        actual_first_response = client.send(first_request)
        actual_second_response = client.send(second_request)

        self.assertIs(actual_first_response, first_response)
        self.assertIs(actual_second_response, second_response)
        self.assertEqual(client.requests, [first_request, second_request])

    def test_raises_when_scripted_responses_are_exhausted(self):
        client = FakeClient(build_config(), scripted_responses=[])
        request = build_request()

        with self.assertRaisesRegex(
            RuntimeError,
            "No more scripted responses available",
        ):
            client.send(request)

        self.assertEqual(client.requests, [request])

    def test_displays_text_when_response_completed_normally(self):
        response = FakeClient(build_config()).send(build_request())

        output = capture_output(response)

        self.assertEqual(
            response.reason,
            ModelResponseEndReason.COMPLETED_NORMALLY,
        )
        self.assertIn(response.text, output)

    def test_displays_incomplete_message_when_output_limit_reached(self):
        normal_response = FakeClient(build_config()).send(build_request())
        incomplete_response = FakeClient(
            build_config(),
            outcome="max_output_tokens",
        ).send(build_request())

        output = capture_output(incomplete_response)

        self.assertEqual(incomplete_response.text, normal_response.text)
        self.assertEqual(
            incomplete_response.reason,
            ModelResponseEndReason.REQUEST_INCOMPLETE,
        )
        self.assertEqual(
            incomplete_response.incomplete_details.reason,
            "max_output_tokens",
        )
        self.assertIn("Request was incomplete: max_output_tokens", output)
        self.assertNotIn(incomplete_response.text, output)


if __name__ == "__main__":
    unittest.main()

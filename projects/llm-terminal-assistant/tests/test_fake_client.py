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


class FakeClientTests(unittest.TestCase):
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

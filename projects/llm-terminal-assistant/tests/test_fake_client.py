import unittest
from contextlib import redirect_stdout
from io import StringIO

from llm_terminal_assistant.adapter.fake_client import FakeClient
from llm_terminal_assistant.cli import output_model_response
from llm_terminal_assistant.config import ModelConfig
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import (
    ModelRequest,
    ModelResponse,
    ModelResponseEndReason,
)


def build_config() -> ModelConfig:
    return ModelConfig(
        api_key="",
        base_url="",
        model="fake-model",
        provider="faked",
    )


def build_request() -> ModelRequest:
    return ModelRequest(
        messages=[Message(role="user", content="test prompt")],
        reserved_output_tokens=128,
    )


def capture_output(response: ModelResponse) -> str:
    output = StringIO()
    with redirect_stdout(output):
        output_model_response(response)
    return output.getvalue()


class FakeClientTests(unittest.TestCase):
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

import unittest
from types import SimpleNamespace

from llm_terminal_assistant.adapter.openai_client import OpenAIClient
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import ModelRequest


class RecordingResponses:
    def __init__(self):
        self.create_kwargs = None

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        return SimpleNamespace(
            model=kwargs["model"],
            output_text="response",
            status="completed",
            usage=SimpleNamespace(
                input_tokens=1,
                input_tokens_details=SimpleNamespace(
                    cached_tokens=0,
                    cache_write_tokens=0,
                ),
                output_tokens=1,
                output_tokens_details=SimpleNamespace(reasoning_tokens=0),
                total_tokens=2,
            ),
            output=[],
        )


class OpenAIClientTests(unittest.TestCase):
    def test_maps_reserved_output_tokens_to_responses_output_limit(self):
        responses = RecordingResponses()
        client = object.__new__(OpenAIClient)
        client.model = "test-model"
        client.client = SimpleNamespace(responses=responses)
        request = ModelRequest(
            messages=[Message(role="user", content="question")],
            reserved_output_tokens=321,
        )

        client.send(request)

        self.assertEqual(responses.create_kwargs["max_output_tokens"], 321)


if __name__ == "__main__":
    unittest.main()

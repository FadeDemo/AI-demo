import unittest
from unittest.mock import patch

from llm_terminal_assistant.budgeter_factory import create_budgeter
from llm_terminal_assistant.cli import send_with_budget_check
from llm_terminal_assistant.client_factory import create_model_client
from llm_terminal_assistant.config import ModelConfig
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import FAKE_MODEL_ID, ModelRequest


def make_config(provider: str = "faked") -> ModelConfig:
    return ModelConfig(
        api_key="",
        base_url="",
        model=FAKE_MODEL_ID,
        provider=provider,
    )


class BudgeterFactoryTests(unittest.TestCase):
    def test_fake_model_path_is_fully_local(self):
        config = make_config()
        with patch.dict(
            "sys.modules",
            {"llm_terminal_assistant.adapter.huggingface_tokenizer": None},
        ):
            budgeter = create_budgeter(config)
            client = create_model_client(config)
        request = ModelRequest(
            messages=[Message(role="user", content="offline request")],
            reserved_output_tokens=config.default_reserved_output_tokens,
        )

        response = send_with_budget_check(client, budgeter, request)

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "This is a fake response")

    def test_fake_model_rejects_non_fake_provider(self):
        with self.assertRaisesRegex(ValueError, "requires the faked provider"):
            create_budgeter(make_config(provider="openai"))


if __name__ == "__main__":
    unittest.main()

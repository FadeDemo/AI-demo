import unittest
from unittest.mock import patch

from llm_terminal_assistant.budgeter_factory import create_budgeter
from llm_terminal_assistant.cli import send_conversation_turn
from llm_terminal_assistant.client_factory import create_model_client
from llm_terminal_assistant.config import ModelConfig
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import FAKE_MODEL_ID


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
        response, trim_result = send_conversation_turn(
            client=client,
            budgeter=budgeter,
            system_message=Message(role="system", content="offline system"),
            completed_turns=[],
            current_user_message=Message(role="user", content="offline request"),
            reserved_output_tokens=config.default_reserved_output_tokens,
            min_reserved_recent_turns=config.min_reserved_recent_turns,
        )

        self.assertEqual(response.text, "This is a fake response")
        self.assertEqual(trim_result.retained_completed_turns, [])
        self.assertEqual(trim_result.dropped_completed_turns_count, 0)

    def test_fake_model_rejects_non_fake_provider(self):
        with self.assertRaisesRegex(ValueError, "requires the faked provider"):
            create_budgeter(make_config(provider="openai"))


if __name__ == "__main__":
    unittest.main()

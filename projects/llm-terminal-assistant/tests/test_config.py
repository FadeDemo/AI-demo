import os
import unittest
from unittest.mock import patch

from llm_terminal_assistant.config import ModelConfig, load_model_config
from llm_terminal_assistant.model import FAKE_MODEL_ID
from llm_terminal_assistant.tools.loop import ToolLoopLimits


class ToolLoopConfigTests(unittest.TestCase):
    def load_config(self, overrides: dict[str, str] | None = None) -> ModelConfig:
        environment = {
            "MODEL": FAKE_MODEL_ID,
            "PROVIDER": "faked",
            "API_KEY": "test-key",
            "BASE_URL": "https://example.invalid",
            **(overrides or {}),
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            patch("llm_terminal_assistant.config.load_dotenv"),
        ):
            return load_model_config()

    def test_missing_limits_use_defaults(self):
        config = self.load_config()

        self.assertEqual(config.tool_loop_limits, ToolLoopLimits(3, 4, 8))

    def test_each_limit_can_be_overridden_without_changing_other_defaults(self):
        cases = (
            ("MAX_TOOL_ROUNDS", ToolLoopLimits(7, 4, 8)),
            ("MAX_MODEL_REQUESTS", ToolLoopLimits(3, 7, 8)),
            ("MAX_TOOL_EXECUTIONS", ToolLoopLimits(3, 4, 7)),
        )
        for name, expected in cases:
            with self.subTest(name=name):
                config = self.load_config({name: "7"})

                self.assertEqual(config.tool_loop_limits, expected)

    def test_limits_are_independent(self):
        config = self.load_config(
            {
                "MAX_TOOL_ROUNDS": "7",
                "MAX_MODEL_REQUESTS": "2",
                "MAX_TOOL_EXECUTIONS": "1",
            }
        )

        self.assertEqual(config.tool_loop_limits, ToolLoopLimits(7, 2, 1))

    def test_invalid_limits_identify_the_configuration_item(self):
        for name in (
            "MAX_TOOL_ROUNDS",
            "MAX_MODEL_REQUESTS",
            "MAX_TOOL_EXECUTIONS",
        ):
            for value in ("", " ", "invalid", "1.5", "0", "-1"):
                with (
                    self.subTest(name=name, value=value),
                    self.assertRaisesRegex(ValueError, name),
                ):
                    self.load_config({name: value})


if __name__ == "__main__":
    unittest.main()

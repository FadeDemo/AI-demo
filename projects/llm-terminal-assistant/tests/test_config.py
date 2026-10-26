import os
import unittest
from unittest.mock import patch

from llm_terminal_assistant.config import (
    ModelConfig,
    RequestRetryConfig,
    RequestTimeoutConfig,
    load_model_config,
)
from llm_terminal_assistant.model import DEEPSEEK_V41_FLASH_1017, FAKE_MODEL_ID
from llm_terminal_assistant.tools.loop import ToolLoopLimits


class RequestTimeoutConfigTests(unittest.TestCase):
    def test_accepts_independent_finite_positive_durations(self):
        config = RequestTimeoutConfig(0.25, 2.5, 10.0, 1.0)

        self.assertEqual(config.connect_seconds, 0.25)
        self.assertEqual(config.first_event_seconds, 2.5)
        self.assertEqual(config.stream_idle_seconds, 10.0)
        self.assertEqual(config.request_deadline_seconds, 1.0)

    def test_rejects_invalid_duration_in_each_field(self):
        valid = {
            "connect_seconds": 1.0,
            "first_event_seconds": 2.0,
            "stream_idle_seconds": 3.0,
            "request_deadline_seconds": 4.0,
        }
        for name in valid:
            for value in (0.0, -1.0, float("nan"), float("inf"), -float("inf")):
                with (
                    self.subTest(field=name, value=value),
                    self.assertRaisesRegex(ValueError, name.upper()),
                ):
                    RequestTimeoutConfig(**{**valid, name: value})


class ModelConfigTests(unittest.TestCase):
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

    def test_missing_stream_output_setting_defaults_to_false(self):
        config = self.load_config()

        self.assertIs(config.stream_output_enabled, False)

    def test_missing_timeout_settings_leave_timeout_config_unset(self):
        config = self.load_config()

        self.assertIsNone(config.request_timeout_config)

    def test_each_timeout_setting_enables_config_with_defaults_for_missing_fields(self):
        cases = (
            ("CONNECT_SECONDS", RequestTimeoutConfig(0.25, 30.0, 30.0, 120.0)),
            ("FIRST_EVENT_SECONDS", RequestTimeoutConfig(10.0, 0.25, 30.0, 120.0)),
            ("STREAM_IDLE_SECONDS", RequestTimeoutConfig(10.0, 30.0, 0.25, 120.0)),
            ("REQUEST_DEADLINE_SECONDS", RequestTimeoutConfig(10.0, 30.0, 30.0, 0.25)),
        )
        for name, expected in cases:
            with self.subTest(name=name):
                config = self.load_config({name: "0.25"})

                self.assertEqual(config.request_timeout_config, expected)

    def test_invalid_timeout_settings_identify_the_configuration_item(self):
        for name in (
            "CONNECT_SECONDS",
            "FIRST_EVENT_SECONDS",
            "STREAM_IDLE_SECONDS",
            "REQUEST_DEADLINE_SECONDS",
        ):
            for value in ("", " ", "invalid", "0", "-1", "nan", "inf", "-inf"):
                with (
                    self.subTest(name=name, value=value),
                    self.assertRaisesRegex(ValueError, name),
                ):
                    self.load_config({name: value})

    def test_missing_retry_settings_use_defaults(self):
        config = self.load_config()

        self.assertEqual(config.request_retry_config, RequestRetryConfig(3, 1.0, 8.0))

    def test_each_retry_setting_can_be_overridden_without_changing_other_defaults(self):
        cases = (
            ("MAX_ATTEMPTS", "1", RequestRetryConfig(1, 1.0, 8.0)),
            ("BASE_DELAY_SECONDS", "0.25", RequestRetryConfig(3, 0.25, 8.0)),
            ("MAX_DELAY_SECONDS", "0.5", RequestRetryConfig(3, 1.0, 0.5)),
        )
        for name, value, expected in cases:
            with self.subTest(name=name, value=value):
                config = self.load_config({name: value})

                self.assertEqual(config.request_retry_config, expected)

    def test_invalid_retry_attempts_identify_the_configuration_item(self):
        for value in ("", " ", "invalid", "1.5", "1e2", "0", "-1", "nan", "inf"):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "MAX_ATTEMPTS"),
            ):
                self.load_config({"MAX_ATTEMPTS": value})

    def test_invalid_retry_delays_identify_the_configuration_item(self):
        for name in ("BASE_DELAY_SECONDS", "MAX_DELAY_SECONDS"):
            for value in ("", " ", "invalid", "0", "-1", "nan", "inf", "-inf", "1e309"):
                with (
                    self.subTest(name=name, value=value),
                    self.assertRaisesRegex(ValueError, name),
                ):
                    self.load_config({name: value})

    def test_deepseek_api_id_resolves_to_1017_profile(self):
        config = self.load_config({"MODEL": "deepseek-flash", "PROVIDER": "openai"})

        self.assertEqual(config.model, "deepseek-flash")
        self.assertIs(config.model_profile, DEEPSEEK_V41_FLASH_1017)

    def test_stream_output_setting_parses_booleans_ignoring_case_and_whitespace(self):
        cases = (
            ("true", True),
            ("false", False),
            ("TRUE", True),
            ("FALSE", False),
            (" TrUe \t", True),
            ("\t FaLsE ", False),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                config = self.load_config({"STREAM_OUTPUT_ENABLED": value})

                self.assertIs(config.stream_output_enabled, expected)

    def test_invalid_stream_output_setting_identifies_the_configuration_item(self):
        for value in ("", " ", "invalid", "1", "0", "yes", "no", "true false"):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "STREAM_OUTPUT_ENABLED"),
            ):
                self.load_config({"STREAM_OUTPUT_ENABLED": value})

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

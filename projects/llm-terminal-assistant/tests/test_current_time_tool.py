import unittest
from datetime import UTC, datetime

from llm_terminal_assistant.tools.current_time import create_current_time_tool
from llm_terminal_assistant.tools.errors import ToolExecutionErrorCategory
from llm_terminal_assistant.tools.executor import ToolExecutor
from llm_terminal_assistant.tools.registry import ToolRegistry


class RecordingClock:
    def __init__(self, current_time: datetime):
        self.current_time = current_time
        self.call_count = 0

    def __call__(self) -> datetime:
        self.call_count += 1
        return self.current_time


def make_executor(clock: RecordingClock) -> ToolExecutor:
    tool = create_current_time_tool(clock)
    return ToolExecutor(ToolRegistry([tool]))


class CurrentTimeToolTests(unittest.TestCase):
    def test_definition_exposes_strict_timezone_parameter(self):
        clock = RecordingClock(datetime(2026, 9, 22, 4, 0, tzinfo=UTC))

        tool = create_current_time_tool(clock)

        self.assertEqual(tool.definition.name, "get_current_time")
        self.assertEqual(
            tool.definition.parameter_schema,
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "required": ["timezone"],
                "properties": {
                    "timezone": {
                        "type": "string",
                        "minLength": 1,
                    }
                },
            },
        )

    def test_converts_fixed_utc_time_to_requested_timezone(self):
        clock = RecordingClock(datetime(2026, 9, 22, 4, 0, tzinfo=UTC))
        executor = make_executor(clock)

        result = executor.execute(
            "get_current_time",
            {"timezone": "Asia/Shanghai"},
        )

        self.assertEqual(
            result.output,
            {
                "timezone": "Asia/Shanghai",
                "current_time": "2026-09-22T12:00:00+08:00",
            },
        )
        self.assertIsNone(result.error)
        self.assertEqual(clock.call_count, 1)

    def test_returns_fixed_time_in_utc(self):
        clock = RecordingClock(datetime(2026, 9, 22, 4, 0, tzinfo=UTC))
        executor = make_executor(clock)

        result = executor.execute(
            "get_current_time",
            {"timezone": "UTC"},
        )

        self.assertEqual(
            result.output,
            {
                "timezone": "UTC",
                "current_time": "2026-09-22T04:00:00+00:00",
            },
        )
        self.assertIsNone(result.error)
        self.assertEqual(clock.call_count, 1)

    def test_unknown_timezone_returns_invalid_arguments_without_reading_clock(self):
        clock = RecordingClock(datetime(2026, 9, 22, 4, 0, tzinfo=UTC))
        executor = make_executor(clock)

        result = executor.execute(
            "get_current_time",
            {"timezone": "Not/A-Timezone"},
        )

        self.assertIsNone(result.output)
        self.assertIsNotNone(result.error)
        self.assertEqual(
            result.error.category,
            ToolExecutionErrorCategory.INVALID_ARGUMENTS,
        )
        self.assertEqual(clock.call_count, 0)

    def test_schema_rejects_invalid_arguments_without_reading_clock(self):
        invalid_arguments = {
            "empty timezone": {"timezone": ""},
            "wrong timezone type": {"timezone": 8},
            "additional field": {
                "timezone": "Asia/Shanghai",
                "unexpected": True,
            },
        }

        for name, arguments in invalid_arguments.items():
            with self.subTest(name=name):
                clock = RecordingClock(datetime(2026, 9, 22, 4, 0, tzinfo=UTC))
                executor = make_executor(clock)

                result = executor.execute("get_current_time", arguments)

                self.assertIsNone(result.output)
                self.assertIsNotNone(result.error)
                self.assertEqual(
                    result.error.category,
                    ToolExecutionErrorCategory.INVALID_ARGUMENTS,
                )
                self.assertEqual(clock.call_count, 0)


if __name__ == "__main__":
    unittest.main()

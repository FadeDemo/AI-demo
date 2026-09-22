import unittest
from datetime import UTC, datetime

from llm_terminal_assistant.tools.executor import ToolExecutor
from llm_terminal_assistant.tools.factory import create_default_tool_registry


class ToolFactoryTests(unittest.TestCase):
    def test_default_registry_contains_current_time_tool(self):
        registry = create_default_tool_registry()

        definitions = registry.get_tool_list()

        self.assertEqual(
            [definition.name for definition in definitions],
            ["get_current_time"],
        )
        self.assertEqual(
            registry.get_tool("get_current_time").definition,
            definitions[0],
        )

    def test_current_time_tool_uses_injected_clock(self):
        fixed_time = datetime(2026, 9, 22, 4, 0, tzinfo=UTC)
        executor = ToolExecutor(create_default_tool_registry(lambda: fixed_time))

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


if __name__ == "__main__":
    unittest.main()

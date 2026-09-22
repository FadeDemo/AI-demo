import unittest

from llm_terminal_assistant.tools.definition import (
    RegisteredTool,
    ToolArguments,
    ToolDefinition,
    ToolHandler,
    ToolOutput,
)
from llm_terminal_assistant.tools.errors import UnknownToolError
from llm_terminal_assistant.tools.registry import ToolRegistry


def first_handler(arguments: ToolArguments) -> ToolOutput:
    return {"handler": "first", "arguments": dict(arguments)}


def second_handler(arguments: ToolArguments) -> ToolOutput:
    return {"handler": "second", "arguments": dict(arguments)}


def make_tool(name: str, handler: ToolHandler) -> RegisteredTool:
    return RegisteredTool(
        definition=ToolDefinition(
            name=name,
            description=f"Execute the {name} test tool.",
            parameter_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        ),
        handler=handler,
    )


class ToolRegistryTests(unittest.TestCase):
    def test_lists_registered_tool_definitions_in_registration_order(self):
        first_tool = make_tool("first", first_handler)
        second_tool = make_tool("second", second_handler)
        registry = ToolRegistry([first_tool, second_tool])

        definitions = registry.get_tool_list()

        self.assertEqual(
            definitions,
            [first_tool.definition, second_tool.definition],
        )

    def test_get_tool_returns_each_registered_tool(self):
        first_tool = make_tool("first", first_handler)
        second_tool = make_tool("second", second_handler)
        registry = ToolRegistry([first_tool, second_tool])

        self.assertIs(registry.get_tool("first"), first_tool)
        self.assertIs(registry.get_tool("second"), second_tool)

    def test_rejects_duplicate_tool_names(self):
        first_tool = make_tool("duplicate", first_handler)
        second_tool = make_tool("duplicate", second_handler)

        with self.assertRaisesRegex(
            ValueError,
            "Duplicate tool name 'duplicate' in registry",
        ):
            ToolRegistry([first_tool, second_tool])

    def test_rejects_unknown_tool_name(self):
        registry = ToolRegistry([make_tool("first", first_handler)])

        with self.assertRaisesRegex(
            UnknownToolError,
            "Tool 'missing' not found in registry",
        ):
            registry.get_tool("missing")


if __name__ == "__main__":
    unittest.main()

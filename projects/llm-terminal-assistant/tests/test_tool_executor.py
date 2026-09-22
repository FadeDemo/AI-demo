import unittest

from llm_terminal_assistant.tools.definition import (
    RegisteredTool,
    ToolArguments,
    ToolDefinition,
    ToolOutput,
)
from llm_terminal_assistant.tools.errors import ToolExecutionErrorCategory
from llm_terminal_assistant.tools.executor import ToolExecutor
from llm_terminal_assistant.tools.registry import ToolRegistry


class RecordingHandler:
    def __init__(
        self,
        output: ToolOutput | None = None,
        error: Exception | None = None,
    ):
        self.output = output or {"status": "ok"}
        self.error = error
        self.calls: list[dict[str, object]] = []

    def __call__(self, arguments: ToolArguments) -> ToolOutput:
        self.calls.append(dict(arguments))
        if self.error is not None:
            raise self.error
        return self.output


def make_executor(handler: RecordingHandler) -> ToolExecutor:
    tool = RegisteredTool(
        definition=ToolDefinition(
            name="example_tool",
            description="Execute an example tool for tests.",
            parameter_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["value"],
                "properties": {
                    "value": {"type": "integer"},
                },
            },
        ),
        handler=handler,
    )
    return ToolExecutor(ToolRegistry([tool]))


class ToolExecutorTests(unittest.TestCase):
    def test_valid_arguments_execute_handler_once_and_return_output(self):
        expected_output = {"doubled": 42}
        handler = RecordingHandler(output=expected_output)
        executor = make_executor(handler)

        result = executor.execute("example_tool", {"value": 21})

        self.assertEqual(result.output, expected_output)
        self.assertIsNone(result.error)
        self.assertEqual(handler.calls, [{"value": 21}])

    def test_invalid_arguments_are_rejected_before_handler_execution(self):
        invalid_arguments = {
            "missing required field": {},
            "wrong field type": {"value": "21"},
            "additional field": {"value": 21, "unexpected": True},
        }

        for name, arguments in invalid_arguments.items():
            with self.subTest(name=name):
                handler = RecordingHandler()
                executor = make_executor(handler)

                result = executor.execute("example_tool", arguments)

                self.assertIsNone(result.output)
                self.assertIsNotNone(result.error)
                self.assertEqual(
                    result.error.category,
                    ToolExecutionErrorCategory.INVALID_ARGUMENTS,
                )
                self.assertEqual(handler.calls, [])

    def test_unknown_tool_is_rejected_without_executing_registered_handler(self):
        handler = RecordingHandler()
        executor = make_executor(handler)

        result = executor.execute("missing_tool", {"value": 21})

        self.assertIsNone(result.output)
        self.assertIsNotNone(result.error)
        self.assertEqual(
            result.error.category,
            ToolExecutionErrorCategory.UNKNOWN_TOOL,
        )
        self.assertEqual(handler.calls, [])

    def test_unexpected_handler_error_returns_safe_execution_failure(self):
        sensitive_detail = "internal path: /private/service/config.json"
        handler = RecordingHandler(error=RuntimeError(sensitive_detail))
        executor = make_executor(handler)

        result = executor.execute("example_tool", {"value": 21})

        self.assertIsNone(result.output)
        self.assertIsNotNone(result.error)
        self.assertEqual(
            result.error.category,
            ToolExecutionErrorCategory.EXECUTION_FAILED,
        )
        self.assertNotIn(sensitive_detail, result.error.message)
        self.assertEqual(handler.calls, [{"value": 21}])


if __name__ == "__main__":
    unittest.main()

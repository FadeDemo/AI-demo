import json
import unittest

from llm_terminal_assistant.tools.definition import (
    RegisteredTool,
    ToolArguments,
    ToolDefinition,
    ToolOutput,
)
from llm_terminal_assistant.tools.errors import (
    InvalidToolArgumentsError,
    ToolExecutionErrorCategory,
)
from llm_terminal_assistant.tools.executor import ToolExecutor
from llm_terminal_assistant.tools.protocol import ToolCallRequest, ToolCallResult
from llm_terminal_assistant.tools.registry import ToolRegistry


class RecordingHandler:
    def __init__(
        self,
        output: ToolOutput | None = None,
        error: Exception | None = None,
    ):
        self.output = output if output is not None else {"status": "ok"}
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


class ToolCallExecutionTests(unittest.TestCase):
    def decode_result(self, result: ToolCallResult) -> dict[str, object]:
        self.assertIsInstance(result, ToolCallResult)
        self.assertEqual(result.call_id, "call-1")
        self.assertIsInstance(result.output, str)
        return json.loads(result.output)

    def test_valid_call_returns_original_output_and_executes_once(self):
        for output in ({"doubled": 42, "text": "测试"}, {}):
            with self.subTest(output=output):
                handler = RecordingHandler(output=output)
                executor = make_executor(handler)
                call = ToolCallRequest("call-1", "example_tool", '{"value":21}')

                result = executor.execute_call(call)

                self.assertEqual(self.decode_result(result), output)
                self.assertEqual(handler.calls, [{"value": 21}])
                self.assertEqual(
                    call,
                    ToolCallRequest("call-1", "example_tool", '{"value":21}'),
                )

    def test_invalid_json_returns_error_without_executing_handler(self):
        for arguments in ("", "{", '{"value":', "not JSON"):
            with self.subTest(arguments=arguments):
                handler = RecordingHandler()

                result = make_executor(handler).execute_call(
                    ToolCallRequest("call-1", "example_tool", arguments)
                )

                self.assertEqual(
                    self.decode_result(result),
                    {
                        "error": {
                            "category": "invalid_arguments",
                            "message": "Tool arguments must be valid JSON.",
                        }
                    },
                )
                self.assertEqual(handler.calls, [])

    def test_non_object_json_returns_error_without_executing_handler(self):
        for arguments in ("[]", "[1]", "null", "true", "21", "1.5", '"text"'):
            with self.subTest(arguments=arguments):
                handler = RecordingHandler()

                result = make_executor(handler).execute_call(
                    ToolCallRequest("call-1", "example_tool", arguments)
                )

                self.assertEqual(
                    self.decode_result(result),
                    {
                        "error": {
                            "category": "invalid_arguments",
                            "message": "Tool arguments must be a JSON object.",
                        }
                    },
                )
                self.assertEqual(handler.calls, [])

    def test_schema_errors_are_preserved_without_executing_handler(self):
        for arguments in ({}, {"value": "21"}, {"value": 21, "extra": True}):
            with self.subTest(arguments=arguments):
                handler = RecordingHandler()
                executor = make_executor(handler)
                expected_error = executor.execute("example_tool", arguments).error

                result = executor.execute_call(
                    ToolCallRequest("call-1", "example_tool", json.dumps(arguments))
                )

                self.assertEqual(
                    self.decode_result(result),
                    {
                        "error": {
                            "category": "invalid_arguments",
                            "message": expected_error.message,
                        }
                    },
                )
                self.assertEqual(handler.calls, [])

    def test_unknown_tool_returns_error_without_executing_handler(self):
        handler = RecordingHandler()

        result = make_executor(handler).execute_call(
            ToolCallRequest("call-1", "missing_tool", '{"value":21}')
        )

        self.assertEqual(
            self.decode_result(result),
            {
                "error": {
                    "category": "unknown_tool",
                    "message": "Tool 'missing_tool' not found in registry",
                }
            },
        )
        self.assertEqual(handler.calls, [])

    def test_handler_parameter_rejection_returns_invalid_arguments(self):
        handler = RecordingHandler(error=InvalidToolArgumentsError("Rejected value"))

        result = make_executor(handler).execute_call(
            ToolCallRequest("call-1", "example_tool", '{"value":21}')
        )

        self.assertEqual(
            self.decode_result(result),
            {
                "error": {
                    "category": "invalid_arguments",
                    "message": "Invalid arguments for tool 'example_tool': Rejected value",
                }
            },
        )
        self.assertEqual(handler.calls, [{"value": 21}])

    def test_handler_failure_returns_execution_error_without_internal_detail(self):
        internal_detail = "internal failure sentinel"
        handler = RecordingHandler(error=RuntimeError(internal_detail))
        executor = make_executor(handler)

        with self.assertLogs("llm_terminal_assistant.tools.executor", level="ERROR"):
            result = executor.execute_call(
                ToolCallRequest("call-1", "example_tool", '{"value":21}')
            )

        self.assertEqual(
            self.decode_result(result),
            {
                "error": {
                    "category": "execution_failed",
                    "message": "Execution of tool 'example_tool' failed.",
                }
            },
        )
        self.assertNotIn(internal_detail, result.output)
        self.assertEqual(handler.calls, [{"value": 21}])


if __name__ == "__main__":
    unittest.main()

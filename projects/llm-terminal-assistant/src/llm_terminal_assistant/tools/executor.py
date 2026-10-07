import json
import logging
from dataclasses import dataclass

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from llm_terminal_assistant.tools.definition import ToolArguments, ToolOutput
from llm_terminal_assistant.tools.errors import (
    InvalidToolArgumentsError,
    ToolExecutionError,
    ToolExecutionErrorCategory,
    UnknownToolError,
)
from llm_terminal_assistant.tools.loop import ToolExecutionBudget
from llm_terminal_assistant.tools.protocol import (
    ToolCallRequest,
    ToolCallResult,
)
from llm_terminal_assistant.tools.registry import RegisteredTool, ToolRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolExecutionResult:
    output: ToolOutput | None = None
    error: ToolExecutionError | None = None


class ToolExecutor:
    def __init__(self, tool_registry: ToolRegistry):
        self._tool_registry = tool_registry
        self._validators: dict[str, Draft202012Validator] = {}
        for definition in self._tool_registry.get_tool_list():
            self._validators[definition.name] = Draft202012Validator(
                definition.parameter_schema
            )

    def execute(
        self,
        tool_name: str,
        arguments: ToolArguments,
        budget: ToolExecutionBudget | None = None,
    ) -> ToolExecutionResult:
        try:
            tool: RegisteredTool = self._tool_registry.get_tool(tool_name)
        except UnknownToolError as e:
            return ToolExecutionResult(
                error=ToolExecutionError(
                    category=ToolExecutionErrorCategory.UNKNOWN_TOOL,
                    message=str(e),
                )
            )
        try:
            validator = self._validators[tool_name]
            validator.validate(arguments)
        except ValidationError as e:
            return ToolExecutionResult(
                error=ToolExecutionError(
                    category=ToolExecutionErrorCategory.INVALID_ARGUMENTS,
                    message=f"Invalid arguments for tool '{tool_name}': {e.message}",
                )
            )
        if budget is not None:
            budget.consume()
        try:
            logger.info("Executing tool: tool_name=%s", tool_name)
            output: ToolOutput = tool.handler(arguments)
            return ToolExecutionResult(output=output)
        except InvalidToolArgumentsError as e:
            return ToolExecutionResult(
                error=ToolExecutionError(
                    category=ToolExecutionErrorCategory.INVALID_ARGUMENTS,
                    message=f"Invalid arguments for tool '{tool_name}': {e!s}",
                )
            )
        except Exception:
            logger.error("Execution of tool %s failed", tool_name)
            return ToolExecutionResult(
                error=ToolExecutionError(
                    category=ToolExecutionErrorCategory.EXECUTION_FAILED,
                    message=f"Execution of tool '{tool_name}' failed.",
                )
            )

    @staticmethod
    def _error_call_result(
        call_id: str,
        category: ToolExecutionErrorCategory,
        message: str,
    ) -> ToolCallResult:
        return ToolCallResult(
            call_id=call_id,
            output=json.dumps({"error": {"category": category, "message": message}}),
        )

    def execute_call(
        self, call: ToolCallRequest, budget: ToolExecutionBudget | None = None
    ) -> ToolCallResult:
        try:
            arguments = json.loads(call.arguments)
        except json.JSONDecodeError:
            return self._error_call_result(
                call.call_id,
                ToolExecutionErrorCategory.INVALID_ARGUMENTS,
                "Tool arguments must be valid JSON.",
            )
        if not isinstance(arguments, dict):
            return self._error_call_result(
                call.call_id,
                ToolExecutionErrorCategory.INVALID_ARGUMENTS,
                "Tool arguments must be a JSON object.",
            )
        result: ToolExecutionResult = self.execute(call.name, arguments, budget)
        if result.error is not None:
            return self._error_call_result(
                call.call_id,
                result.error.category,
                result.error.message,
            )
        return ToolCallResult(call_id=call.call_id, output=json.dumps(result.output))

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

    def execute(self, tool_name: str, arguments: ToolArguments) -> ToolExecutionResult:
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
        try:
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
            logger.exception("Execution of tool %s failed", tool_name)
            return ToolExecutionResult(
                error=ToolExecutionError(
                    category=ToolExecutionErrorCategory.EXECUTION_FAILED,
                    message=f"Execution of tool '{tool_name}' failed.",
                )
            )

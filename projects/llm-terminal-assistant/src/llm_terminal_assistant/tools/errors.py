from dataclasses import dataclass
from enum import StrEnum


class ToolExecutionErrorCategory(StrEnum):
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENTS = "invalid_arguments"
    EXECUTION_FAILED = "execution_failed"


@dataclass(frozen=True)
class ToolExecutionError:
    category: ToolExecutionErrorCategory
    message: str


class UnknownToolError(LookupError):
    pass


class InvalidToolArgumentsError(ValueError):
    pass


class ToolLoopStopReason(StrEnum):
    MAX_TOOL_ROUNDS_REACHED = "max_tool_rounds_reached"
    MAX_MODEL_REQUESTS_REACHED = "max_model_requests_reached"
    MAX_TOOL_EXECUTIONS_REACHED = "max_tool_executions_reached"


class ToolLoopStoppedError(RuntimeError):
    def __init__(self, reason: ToolLoopStopReason):
        self.reason = reason
        super().__init__(f"Tool loop stopped due to: {reason.value}")

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

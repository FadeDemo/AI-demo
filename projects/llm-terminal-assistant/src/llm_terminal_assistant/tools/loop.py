from dataclasses import dataclass

from llm_terminal_assistant.tools.errors import ToolLoopStoppedError, ToolLoopStopReason


@dataclass(frozen=True)
class ToolLoopLimits:
    max_tool_rounds: int = 3
    max_model_requests: int = 4
    max_tool_executions: int = 8


@dataclass
class ToolExecutionBudget:
    max_tool_executions: int
    used_tool_executions: int = 0

    def consume(self):
        if self.used_tool_executions >= self.max_tool_executions:
            raise ToolLoopStoppedError(ToolLoopStopReason.MAX_TOOL_EXECUTIONS_REACHED)
        self.used_tool_executions += 1

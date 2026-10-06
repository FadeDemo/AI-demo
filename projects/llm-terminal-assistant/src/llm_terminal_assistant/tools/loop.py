from dataclasses import dataclass


@dataclass(frozen=True)
class ToolLoopLimits:
    max_tool_rounds: int = 3
    max_model_requests: int = 4
    max_tool_executions: int = 8

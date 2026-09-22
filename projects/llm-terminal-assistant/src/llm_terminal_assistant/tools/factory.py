from llm_terminal_assistant.tools.current_time import (
    Clock,
    create_current_time_tool,
    system_clock,
)
from llm_terminal_assistant.tools.registry import ToolRegistry


def create_default_tool_registry(
    clock: Clock = system_clock,
) -> ToolRegistry:
    tools = [
        create_current_time_tool(clock),
    ]
    return ToolRegistry(tools)

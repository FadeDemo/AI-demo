from llm_terminal_assistant.tools.definition import RegisteredTool, ToolDefinition
from llm_terminal_assistant.tools.errors import UnknownToolError


class ToolRegistry:
    def __init__(self, tools: list[RegisteredTool]):
        self._tools: dict[str, RegisteredTool] = {}
        for tool in tools:
            if tool.definition.name in self._tools:
                raise ValueError(
                    f"Duplicate tool name '{tool.definition.name}' in registry"
                )
            self._tools[tool.definition.name] = tool

    def get_tool_list(self) -> list[ToolDefinition]:
        return [tool.definition for tool in self._tools.values()]

    def get_tool(self, name: str) -> RegisteredTool:
        tool = self._tools.get(name)
        if tool is None:
            raise UnknownToolError(f"Tool '{name}' not found in registry")
        return tool

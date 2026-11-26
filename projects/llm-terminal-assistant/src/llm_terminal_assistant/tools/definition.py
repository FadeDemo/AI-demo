from collections.abc import Callable, Mapping
from dataclasses import dataclass

from llm_shared.tools.definition import ToolDefinition

type ToolArguments = Mapping[str, object]
type ToolOutput = dict[str, object]
type ToolHandler = Callable[[ToolArguments], ToolOutput]


@dataclass
class RegisteredTool:
    definition: ToolDefinition
    handler: ToolHandler

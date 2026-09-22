from collections.abc import Callable, Mapping
from dataclasses import dataclass

type JsonSchema = dict[str, object]
type ToolArguments = Mapping[str, object]
type ToolOutput = dict[str, object]
type ToolHandler = Callable[[ToolArguments], ToolOutput]


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameter_schema: JsonSchema


@dataclass
class RegisteredTool:
    definition: ToolDefinition
    handler: ToolHandler

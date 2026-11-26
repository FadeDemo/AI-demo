from dataclasses import dataclass

type JsonSchema = dict[str, object]


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameter_schema: JsonSchema

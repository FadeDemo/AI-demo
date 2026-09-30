from dataclasses import dataclass


@dataclass
class ToolCallRequest:
    call_id: str
    name: str
    arguments: str


@dataclass
class ToolCallResult:
    call_id: str
    output: str

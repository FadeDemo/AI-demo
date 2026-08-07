from __future__ import annotations

from dataclasses import dataclass

from llm_terminal_assistant.message import Message


@dataclass
class ModelRequest:
    messages: list[Message]


@dataclass
class ModelResponse:
    text: str
    reason: str
    usage: ModelUsage
    name: str


@dataclass
class ModelUsage:
    input_tokens: int
    input_tokens_details: InputTokensDetails
    output_tokens: int
    output_tokens_details: OutputTokensDetails
    total_tokens: int


@dataclass
class InputTokensDetails:
    cached_tokens: int
    cache_write_tokens: int


@dataclass
class OutputTokensDetails:
    reasoning_tokens: int

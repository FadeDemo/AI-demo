from dataclasses import dataclass
from typing import Literal

from llm_terminal_assistant._vendor.deepseek_ai.deepseek_v4 import encode_messages
from llm_terminal_assistant.model import ModelRequest

_REASONING_EFFORT_MAPPING = {
    "low": "low",
    "medium": "high",
    "high": "high",
    "xhigh": "high",
    "max": "max",
}


@dataclass(frozen=True)
class _ResolvedReasoning:
    thinking_mode: Literal["chat", "thinking"]
    reasoning_effort: str | None


def _normalize_reasoning_effort(reasoning_effort: str) -> str:
    try:
        return _REASONING_EFFORT_MAPPING[reasoning_effort]
    except KeyError:
        raise ValueError(f"Unsupported reasoning effort: {reasoning_effort}") from None


def encode_deepseek_request(
    request: ModelRequest,
    thinking_mode: str,
) -> str:
    messages = [
        {
            "role": message.role,
            "content": message.content,
        }
        for message in request.messages
    ]

    return encode_messages(
        messages=messages,
        thinking_mode=thinking_mode,
        reasoning_effort=_normalize_reasoning_effort(request.reasoning_effort),
    )

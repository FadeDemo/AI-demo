from dataclasses import dataclass
from typing import Literal

from llm_terminal_assistant._vendor.deepseek_ai.deepseek_v4 import encode_messages
from llm_terminal_assistant.model import ModelRequest
from llm_terminal_assistant.request_encoder import RequestEncoder

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


def _resolve_reasoning_effort(
    requested_effort: str | None,
    default_effort: str,
) -> _ResolvedReasoning:
    """Resolve Responses API reasoning settings for DeepSeek encoding."""

    effective_effort = default_effort if requested_effort is None else requested_effort

    if effective_effort == "none":
        return _ResolvedReasoning(
            thinking_mode="chat",
            reasoning_effort=None,
        )

    return _ResolvedReasoning(
        thinking_mode="thinking",
        reasoning_effort=_normalize_reasoning_effort(effective_effort),
    )


def encode_deepseek_request(
    request: ModelRequest,
    default_reasoning_effort: str,
) -> str:
    reasoning = _resolve_reasoning_effort(
        requested_effort=request.reasoning_effort,
        default_effort=default_reasoning_effort,
    )
    messages = [
        {
            "role": message.role,
            "content": message.content,
        }
        for message in request.messages
    ]

    return encode_messages(
        messages=messages,
        thinking_mode=reasoning.thinking_mode,
        reasoning_effort=reasoning.reasoning_effort,
    )


class DeepSeekRequestEncoder(RequestEncoder):
    def __init__(self, default_reasoning_effort: str):
        self.default_reasoning_effort = default_reasoning_effort

    def encode_request(self, request: ModelRequest) -> str:
        return encode_deepseek_request(
            request=request,
            default_reasoning_effort=self.default_reasoning_effort,
        )

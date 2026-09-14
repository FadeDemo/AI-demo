from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from llm_terminal_assistant.model import ModelProfile, ModelRequest, PromptFormat
from llm_terminal_assistant.request_encoder import RequestEncoder

_REASONING_EFFORT_MAPPING = {
    "minimal": "low",
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


type DeepSeekMessageEncoder = Callable[..., str]


def encode_deepseek_request(
    request: ModelRequest,
    default_reasoning_effort: str,
    deepseek_message_encoder: DeepSeekMessageEncoder,
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

    return deepseek_message_encoder(
        messages=messages,
        thinking_mode=reasoning.thinking_mode,
        reasoning_effort=reasoning.reasoning_effort,
    )


@dataclass
class DeepSeekRequestEncoder(RequestEncoder):
    default_reasoning_effort: str
    deepseek_message_encoder: DeepSeekMessageEncoder

    def encode_request(self, request: ModelRequest) -> str:
        return encode_deepseek_request(
            request=request,
            default_reasoning_effort=self.default_reasoning_effort,
            deepseek_message_encoder=self.deepseek_message_encoder,
        )


def create_deepseek_request_encoder(
    model_profile: ModelProfile,
) -> DeepSeekRequestEncoder:
    match model_profile.prompt_format:
        case PromptFormat.DEEPSEEK_V4:
            from llm_terminal_assistant._vendor.deepseek_ai.deepseek_v4 import (
                encode_messages,
            )
        case PromptFormat.DEEPSEEK_V41:
            from llm_terminal_assistant._vendor.deepseek_ai.deepseek_v41 import (
                encode_messages,
            )
        case _:
            raise ValueError(
                f"Unsupported prompt format for DeepSeek encoding: {model_profile.prompt_format}"
            )
    return DeepSeekRequestEncoder(
        default_reasoning_effort=model_profile.default_reasoning_effort,
        deepseek_message_encoder=encode_messages,
    )

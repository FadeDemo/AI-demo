from __future__ import annotations

from dataclasses import dataclass, field

from llm_terminal_assistant.message import Message


@dataclass
class ModelRequest:
    messages: list[Message]
    reasoning_effort: str | None = None


@dataclass
class ModelResponse:
    text: str
    reason: str
    usage: ModelUsage
    tool_calls: list[ToolCallRequest] = field(default_factory=list)


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


@dataclass
class ToolCallRequest:
    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ModelProfile:
    api_model_id: str
    repository: str
    revision: str
    limit: ModelLimits
    default_reasoning_effort: str
    allowed_reasoning_efforts: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelLimits:
    context_window_tokens: int
    max_output_tokens: int | None = None
    max_input_tokens: int | None = None


DEEPSEEK_V4_FLASH = ModelProfile(
    api_model_id="deepseek-v4-flash",
    repository="deepseek-ai/DeepSeek-V4-Flash-0731",
    revision="7872f01b1d1fe23eabc4c98b48bffcef5a386062",
    limit=ModelLimits(context_window_tokens=1_000_000, max_output_tokens=384_000),
    allowed_reasoning_efforts=("low", "medium", "high", "xhign", "max"),
    default_reasoning_effort="high",
)

MODEL_PROFILES = {
    DEEPSEEK_V4_FLASH.api_model_id: DEEPSEEK_V4_FLASH,
}

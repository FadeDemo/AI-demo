from __future__ import annotations

from dataclasses import dataclass, field

from llm_terminal_assistant.message import Message


@dataclass
class ModelRequest:
    messages: list[Message]
    reserved_output_tokens: int
    reasoning_effort: str | None = None
    temperature: float | None = None
    top_p: float | None = None


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
class TemperatureConfig:
    default_temperature: float
    min_temperature: float
    max_temperature: float


@dataclass(frozen=True)
class TopPConfig:
    default_top_p: float
    min_top_p: float
    max_top_p: float


@dataclass(frozen=True)
class ModelProfile:
    api_model_id: str
    repository: str
    revision: str
    limit: ModelLimits
    default_reasoning_effort: str
    temperature_config: TemperatureConfig
    top_p_config: TopPConfig
    allowed_reasoning_efforts: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelLimits:
    context_window_tokens: int
    max_output_tokens: int | None = None
    max_input_tokens: int | None = None


FAKE_MODEL_ID = "fake-model"
FAKE_MODEL_LIMITS = ModelLimits(
    context_window_tokens=32_768,
    max_output_tokens=8_192,
    max_input_tokens=16_384,
)
FAKE_MODEL_PROFILE = ModelProfile(
    api_model_id=FAKE_MODEL_ID,
    repository="fake-repo/fake-model",
    revision="fake-revision",
    limit=FAKE_MODEL_LIMITS,
    default_reasoning_effort="none",
    allowed_reasoning_efforts=("none",),
    temperature_config=TemperatureConfig(
        default_temperature=1.0,
        min_temperature=0.0,
        max_temperature=2.0,
    ),
    top_p_config=TopPConfig(
        default_top_p=1.0,
        min_top_p=0.0,
        max_top_p=1.0,
    ),
)


DEEPSEEK_V4_FLASH = ModelProfile(
    api_model_id="deepseek-v4-flash",
    repository="deepseek-ai/DeepSeek-V4-Flash-0731",
    revision="7872f01b1d1fe23eabc4c98b48bffcef5a386062",
    limit=ModelLimits(context_window_tokens=1_000_000, max_output_tokens=384_000),
    allowed_reasoning_efforts=("low", "medium", "high", "xhigh", "max"),
    default_reasoning_effort="high",
    temperature_config=TemperatureConfig(
        default_temperature=1.0,
        min_temperature=0.0,
        max_temperature=2.0,
    ),
    top_p_config=TopPConfig(
        default_top_p=1.0,
        min_top_p=0.0,
        max_top_p=1.0,
    ),
)

MODEL_PROFILES = {
    DEEPSEEK_V4_FLASH.api_model_id: DEEPSEEK_V4_FLASH,
    FAKE_MODEL_PROFILE.api_model_id: FAKE_MODEL_PROFILE,
}

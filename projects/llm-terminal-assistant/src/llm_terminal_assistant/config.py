import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from llm_terminal_assistant.model import (
    CURRENT_PROFILE_BY_API_MODEL_ID,
    MODEL_PROFILES,
    ModelProfile,
)
from llm_terminal_assistant.tools.loop import ToolLoopLimits

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


@dataclass
class RequestTimeoutConfig:
    connect_seconds: float
    first_event_seconds: float
    stream_idle_seconds: float
    request_deadline_seconds: float

    def __post_init__(self):
        if self.connect_seconds <= 0 or not math.isfinite(self.connect_seconds):
            raise ValueError(
                f"CONNECT_SECONDS must be a positive finite number, got {self.connect_seconds}."
            )
        if self.first_event_seconds <= 0 or not math.isfinite(self.first_event_seconds):
            raise ValueError(
                f"FIRST_EVENT_SECONDS must be a positive finite number, got {self.first_event_seconds}."
            )
        if self.stream_idle_seconds <= 0 or not math.isfinite(self.stream_idle_seconds):
            raise ValueError(
                f"STREAM_IDLE_SECONDS must be a positive finite number, got {self.stream_idle_seconds}."
            )
        if self.request_deadline_seconds <= 0 or not math.isfinite(
            self.request_deadline_seconds
        ):
            raise ValueError(
                f"REQUEST_DEADLINE_SECONDS must be a positive finite number, got {self.request_deadline_seconds}."
            )


@dataclass
class RequestRetryConfig:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 8.0

    def __post_init__(self):
        if self.max_attempts <= 0:
            raise ValueError(
                f"MAX_ATTEMPTS must be a positive integer, got {self.max_attempts}."
            )
        if self.base_delay_seconds <= 0 or not math.isfinite(self.base_delay_seconds):
            raise ValueError(
                f"BASE_DELAY_SECONDS must be a positive finite number, got {self.base_delay_seconds}."
            )
        if self.max_delay_seconds <= 0 or not math.isfinite(self.max_delay_seconds):
            raise ValueError(
                f"MAX_DELAY_SECONDS must be a positive finite number, got {self.max_delay_seconds}."
            )


@dataclass
class ModelConfig:
    api_key: str
    base_url: str
    model: str
    model_profile: ModelProfile
    reasoning_effort: str | None = None
    provider: Literal["faked", "openai"] = "faked"
    safety_margin_tokens: int = 1_024
    default_reserved_output_tokens: int = 8192
    min_reserved_recent_turns: int = 1
    temperature: float | None = None
    top_p: float | None = None
    tool_loop_limits: ToolLoopLimits = field(default_factory=ToolLoopLimits)
    stream_output_enabled: bool = False
    request_timeout_config: RequestTimeoutConfig | None = None
    request_retry_config: RequestRetryConfig = field(default_factory=RequestRetryConfig)


def read_positive_int_env(name: str) -> int | None:
    raw_value = os.getenv(name)
    if raw_value is None:
        return None
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer, got {raw_value}.") from error
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {value}.")
    return value


def read_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be a float, got {raw_value}.") from error


def load_model_config() -> ModelConfig:
    load_dotenv(ENV_FILE, override=False)
    api_key = os.getenv("API_KEY")
    base_url = os.getenv("BASE_URL")
    model = os.getenv("MODEL")
    provider = os.getenv("PROVIDER")
    reasoning_effort = os.getenv("REASONING_EFFORT")
    profile_id = CURRENT_PROFILE_BY_API_MODEL_ID.get(model)
    if not profile_id:
        raise ValueError(f"Profile ID for model {model} not found.")
    model_profile = MODEL_PROFILES.get(profile_id)
    if not model_profile:
        raise ValueError(f"Model profile for {model} not found.")
    temperature = os.getenv("TEMPERATURE")
    top_p = os.getenv("TOP_P")
    stream_output_enabled = os.getenv("STREAM_OUTPUT_ENABLED", "false")
    request_timeout_config = None
    if any(
        os.getenv(name) is not None
        for name in (
            "CONNECT_SECONDS",
            "FIRST_EVENT_SECONDS",
            "STREAM_IDLE_SECONDS",
            "REQUEST_DEADLINE_SECONDS",
        )
    ):
        request_timeout_config = RequestTimeoutConfig(
            connect_seconds=read_float_env("CONNECT_SECONDS", 10.0),
            first_event_seconds=read_float_env("FIRST_EVENT_SECONDS", 30.0),
            stream_idle_seconds=read_float_env("STREAM_IDLE_SECONDS", 30.0),
            request_deadline_seconds=read_float_env("REQUEST_DEADLINE_SECONDS", 120.0),
        )
    if temperature is not None:
        temperature = float(temperature)
        if not (
            model_profile.temperature_config.min_temperature
            <= temperature
            <= model_profile.temperature_config.max_temperature
        ):
            raise ValueError(
                f"Temperature {temperature} is out of range for model {model}."
            )
    if top_p is not None:
        top_p = float(top_p)
        if not (
            model_profile.top_p_config.min_top_p
            <= top_p
            <= model_profile.top_p_config.max_top_p
        ):
            raise ValueError(f"TopP {top_p} is out of range for model {model}.")
    tool_loop_limits: dict[str, int] = {}
    for field_name, env_name in (
        ("max_tool_rounds", "MAX_TOOL_ROUNDS"),
        ("max_model_requests", "MAX_MODEL_REQUESTS"),
        ("max_tool_executions", "MAX_TOOL_EXECUTIONS"),
    ):
        value = read_positive_int_env(env_name)
        if value is not None:
            tool_loop_limits[field_name] = value
    if stream_output_enabled is not None:
        stream_output_enabled = stream_output_enabled.strip().lower()
        if stream_output_enabled not in ("true", "false"):
            raise ValueError(
                f"STREAM_OUTPUT_ENABLED must be a boolean, got {stream_output_enabled}."
            )
        stream_output_enabled = stream_output_enabled == "true"
    return ModelConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        provider=provider,
        reasoning_effort=reasoning_effort,
        temperature=temperature,
        top_p=top_p,
        model_profile=model_profile,
        tool_loop_limits=ToolLoopLimits(**tool_loop_limits),
        stream_output_enabled=stream_output_enabled,
        request_timeout_config=request_timeout_config,
    )

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from llm_terminal_assistant.model import (
    CURRENT_PROFILE_BY_API_MODEL_ID,
    MODEL_PROFILES,
    ModelProfile,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


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
    return ModelConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        provider=provider,
        reasoning_effort=reasoning_effort,
        temperature=temperature,
        top_p=top_p,
        model_profile=model_profile,
    )

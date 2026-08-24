import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from llm_terminal_assistant.model import MODEL_PROFILES

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


@dataclass
class ModelConfig:
    api_key: str
    base_url: str
    model: str
    reasoning_effort: str | None = None
    provider: Literal["faked", "openai"] = "faked"
    safety_margin_tokens: int = 1_024
    default_reserved_output_tokens: int = 8192
    min_reserved_recent_turns: int = 1


def load_model_config() -> ModelConfig:
    load_dotenv(ENV_FILE, override=False)
    api_key = os.getenv("API_KEY")
    base_url = os.getenv("BASE_URL")
    model = os.getenv("MODEL")
    provider = os.getenv("PROVIDER")
    reasoning_effort = os.getenv("REASONING_EFFORT")
    model_profile = MODEL_PROFILES.get(model)
    if not model_profile:
        raise ValueError(f"Model profile for {model} not found.")
    return ModelConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        provider=provider,
        reasoning_effort=reasoning_effort,
    )

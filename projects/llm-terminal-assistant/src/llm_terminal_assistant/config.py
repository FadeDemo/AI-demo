import os
from dataclasses import dataclass


@dataclass
class ModelConfig:
    api_key: str
    base_url: str
    model: str


def load_model_config() -> ModelConfig:
    api_key = os.getenv("API_KEY")
    base_url = os.getenv("BASE_URL")
    model = os.getenv("MODEL")

    return ModelConfig(api_key=api_key, base_url=base_url, model=model)

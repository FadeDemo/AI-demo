from llm_terminal_assistant.client import ModelClient
from llm_terminal_assistant.config import ModelConfig


def create_model_client(config: ModelConfig) -> ModelClient:
    if config.provider == "openai":
        from llm_terminal_assistant.adapter.openai_client import OpenAIClient

        return OpenAIClient(config)

    if config.provider == "faked":
        from llm_terminal_assistant.adapter.fake_client import FakeClient

        return FakeClient(config)

    raise ValueError(f"Unsupported provider: {config.provider}")

from llm_terminal_assistant.config import ModelConfig
from llm_terminal_assistant.model import ModelRequest, ModelResponse


class ModelClient:
    def __init__(self, config: ModelConfig):
        self.api_key = config.api_key
        self.base_url = config.base_url
        self.model = config.model

    def send(self, request: ModelRequest) -> ModelResponse: ...

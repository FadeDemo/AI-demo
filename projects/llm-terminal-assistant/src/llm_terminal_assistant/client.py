from collections.abc import Generator
from typing import Protocol

from llm_terminal_assistant.config import ModelConfig
from llm_terminal_assistant.model import ModelRequest, ModelResponse
from llm_terminal_assistant.stream.events import StreamEvent


class ModelClient(Protocol):
    def __init__(self, config: ModelConfig):
        self.api_key = config.api_key
        self.base_url = config.base_url
        self.model = config.model

    def send(self, request: ModelRequest) -> ModelResponse: ...

    def send_stream(self, request: ModelRequest) -> Generator[StreamEvent]: ...

    def validate_reasoning_effort(
        self, effort: str | None, allowed_efforts: tuple[str, ...]
    ) -> None: ...

from collections.abc import AsyncGenerator
from typing import Protocol

from llm_shared.model import ModelRequest, ModelResponse
from llm_shared.stream.events import StreamEvent

from llm_terminal_assistant.config import ModelConfig


class ModelClient(Protocol):
    def __init__(self, config: ModelConfig):
        self.api_key = config.api_key
        self.base_url = config.base_url
        self.model = config.model

    def send(self, request: ModelRequest) -> ModelResponse: ...

    def send_stream(self, request: ModelRequest) -> AsyncGenerator[StreamEvent]: ...

    def validate_reasoning_effort(
        self, effort: str | None, allowed_efforts: tuple[str, ...]
    ) -> None: ...

    async def aclose(self) -> None: ...

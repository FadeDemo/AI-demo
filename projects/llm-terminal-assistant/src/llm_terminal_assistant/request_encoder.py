from typing import Protocol

from llm_terminal_assistant.model import ModelRequest


class RequestEncoder(Protocol):
    def encode_request(self, request: ModelRequest) -> str: ...

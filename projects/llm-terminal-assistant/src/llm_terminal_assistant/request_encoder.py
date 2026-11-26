from typing import Protocol

from llm_shared.model import ModelRequest


class RequestEncoder(Protocol):
    def encode_request(self, request: ModelRequest) -> str: ...

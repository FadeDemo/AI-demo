import json
from dataclasses import dataclass

from llm_terminal_assistant.model import ModelRequest
from llm_terminal_assistant.request_encoder import RequestEncoder
from llm_terminal_assistant.token_counter import TokenCounter


class FakeModelRequestEncoder(RequestEncoder):
    """Encode the synthetic fake model input as canonical JSON."""

    def encode_request(self, request: ModelRequest) -> str:
        return json.dumps(
            {
                "messages": [
                    {"role": message.role, "content": message.content}
                    for message in request.messages
                ],
                "reasoning_effort": request.reasoning_effort,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


@dataclass(frozen=True)
class CodePointTokenCounter(TokenCounter):
    """Treat each Unicode code point as one synthetic fake-model token."""

    def count_tokens(
        self,
        text: str,
        add_special_tokens: bool = False,
    ) -> int:
        return len(text)

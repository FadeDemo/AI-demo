import json
from dataclasses import dataclass

from llm_terminal_assistant.adapter.protocol_mapping import (
    to_openai_responses_input_item,
)
from llm_terminal_assistant.model import ModelRequest
from llm_terminal_assistant.request_encoder import RequestEncoder
from llm_terminal_assistant.token_counter import TokenCounter


class FakeModelRequestEncoder(RequestEncoder):
    """Encode the synthetic fake model input as canonical JSON."""

    def encode_request(self, request: ModelRequest) -> str:
        return json.dumps(
            {
                "input": [
                    to_openai_responses_input_item(item) for item in request.input
                ],
                "reasoning_effort": request.reasoning_effort,
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "parameter_schema": tool.parameter_schema,
                    }
                    for tool in request.tools
                ],
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

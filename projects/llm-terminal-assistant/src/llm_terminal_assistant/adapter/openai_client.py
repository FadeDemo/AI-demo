import logging
from typing import TYPE_CHECKING

from llm_terminal_assistant.client import ModelClient
from llm_terminal_assistant.config import ModelConfig
from llm_terminal_assistant.model import (
    InputTokensDetails,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    OutputTokensDetails,
    ToolCallRequest,
)

if TYPE_CHECKING:
    from openai.types.responses import Response

logger = logging.getLogger(__name__)


class OpenAIClient(ModelClient):
    def __init__(self, config: ModelConfig):
        from openai import OpenAI

        super().__init__(config)
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def send(self, request: ModelRequest) -> ModelResponse:
        openai_response = self.client.responses.create(
            model=self.model,
            input=[
                {"role": msg.role, "content": msg.content} for msg in request.messages
            ],
            max_output_tokens=request.reserved_output_tokens,
        )
        logger.debug("Using model: %s", openai_response.model)
        return ModelResponse(
            text=openai_response.output_text,
            reason=self.derive_end_reason(openai_response),
            usage=ModelUsage(
                input_tokens=openai_response.usage.input_tokens,
                input_tokens_details=InputTokensDetails(
                    cached_tokens=openai_response.usage.input_tokens_details.cached_tokens,
                    cache_write_tokens=openai_response.usage.input_tokens_details.cache_write_tokens,
                ),
                output_tokens=openai_response.usage.output_tokens,
                output_tokens_details=OutputTokensDetails(
                    reasoning_tokens=openai_response.usage.output_tokens_details.reasoning_tokens
                ),
                total_tokens=openai_response.usage.total_tokens,
            ),
            tool_calls=[
                ToolCallRequest(
                    call_id=o.call_id,
                    name=o.name,
                    arguments=o.arguments,
                )
                for o in openai_response.output
                if o.type == "function_call"
            ],
        )

    def derive_end_reason(self, response: "Response") -> str:
        if response.status == "completed":
            return "Completed normally"
        elif response.status == "failed":
            return (
                "Request failed: ["
                + response.error.code
                + "] "
                + response.error.message
            )
        elif response.status == "cancelled":
            return "Request was cancelled"
        elif response.status == "incomplete":
            return "Request was incomplete: " + response.incomplete_details.reason

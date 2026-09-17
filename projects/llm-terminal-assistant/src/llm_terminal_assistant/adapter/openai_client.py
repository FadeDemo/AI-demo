import logging
from typing import TYPE_CHECKING

from llm_terminal_assistant.client import ModelClient
from llm_terminal_assistant.config import ModelConfig
from llm_terminal_assistant.model import (
    InputTokensDetails,
    ModelRequest,
    ModelResponse,
    ModelResponseEndReason,
    ModelResponseError,
    ModelResponseIncompleteDetails,
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
        request_options = {
            "model": self.model,
            "input": [
                {"role": msg.role, "content": msg.content} for msg in request.messages
            ],
            "max_output_tokens": request.reserved_output_tokens,
        }
        if request.reasoning_effort is not None:
            request_options["reasoning"] = {
                "effort": request.reasoning_effort,
            }
        if request.temperature is not None:
            request_options["temperature"] = request.temperature
        if request.top_p is not None:
            request_options["top_p"] = request.top_p
        if request.output_format is not None:
            request_options["text"] = {
                "format": {
                    "type": request.output_format.type,
                    "name": request.output_format.name,
                    "schema": request.output_format.schema,
                }
            }
        openai_response = self.client.responses.create(**request_options)
        logger.debug("Using model: %s", openai_response.model)
        reason, error, incomplete_details = self.derive_end_reason(openai_response)
        return ModelResponse(
            text=openai_response.output_text,
            reason=reason,
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
            error=error,
            incomplete_details=incomplete_details,
        )

    def derive_end_reason(
        self, response: "Response"
    ) -> tuple[
        ModelResponseEndReason,
        ModelResponseError | None,
        ModelResponseIncompleteDetails | None,
    ]:
        if response.status == "completed":
            return ModelResponseEndReason.COMPLETED_NORMALLY, None, None
        elif response.status == "failed":
            return (
                ModelResponseEndReason.REQUEST_FAILED,
                ModelResponseError(
                    code=response.error.code,
                    message=response.error.message,
                ),
                None,
            )
        elif response.status == "cancelled":
            return ModelResponseEndReason.REQUEST_CANCELLED, None, None
        elif response.status == "incomplete":
            return (
                ModelResponseEndReason.REQUEST_INCOMPLETE,
                None,
                ModelResponseIncompleteDetails(
                    reason=response.incomplete_details.reason
                ),
            )

    def validate_reasoning_effort(
        self, effort: str | None, allowed_efforts: tuple[str, ...]
    ) -> None:
        if effort is not None and effort != "none" and effort not in allowed_efforts:
            supported_efforts = ("none", *allowed_efforts)
            raise ValueError(
                f"Reasoning effort '{effort}' is not supported for model '{self.model}'. "
                f"Supported efforts: {supported_efforts}"
            )

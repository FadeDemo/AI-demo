import logging
import math
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from httpx import ReadTimeout, Timeout
from openai import APIConnectionError, APIStatusError

from llm_terminal_assistant.adapter.protocol_mapping import (
    to_openai_responses_input_item,
)
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
)
from llm_terminal_assistant.stream.events import (
    EndEvent,
    StreamEvent,
    TextDeltaEvent,
    UsageEvent,
)
from llm_terminal_assistant.tools.protocol import ToolCallRequest

if TYPE_CHECKING:
    from openai.types.responses import Response

logger = logging.getLogger(__name__)


class OpenAIClient(ModelClient):
    def __init__(self, config: ModelConfig):
        self.client = None
        self.stream_client = None

        super().__init__(config)
        self.constructor_kwargs = {
            "api_key": self.api_key,
            "base_url": self.base_url,
        }
        if config.request_timeout_config is not None:
            from openai import DEFAULT_TIMEOUT

            timeout = Timeout(DEFAULT_TIMEOUT)
            timeout.connect = config.request_timeout_config.connect_seconds
            self.constructor_kwargs["timeout"] = timeout

    def _build_request_options(self, request: ModelRequest) -> dict[str, object]:
        request_options: dict[str, object] = {
            "model": self.model,
            "input": [to_openai_responses_input_item(item) for item in request.input],
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
        if request.tools:
            request_options["tools"] = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameter_schema,
                }
                for tool in request.tools
            ]
        return request_options

    def _parse_retry_after(
        self,
        retry_after: str | None,
    ) -> float | None:
        if retry_after is not None:
            try:
                retry_after = float(retry_after)
                if retry_after < 0 or not math.isfinite(retry_after):
                    return None
                return retry_after
            except ValueError:
                return None
        return None

    def send(self, request: ModelRequest) -> ModelResponse:
        if self.client is None:
            from openai import OpenAI

            self.client = OpenAI(**self.constructor_kwargs)
        request_options = self._build_request_options(request)
        openai_response = self.client.responses.create(**request_options)
        logger.debug("Using model: %s", self.model)
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

    async def send_stream(self, request: ModelRequest) -> AsyncGenerator[StreamEvent]:
        if self.stream_client is None:
            from openai import AsyncOpenAI

            self.stream_client = AsyncOpenAI(**self.constructor_kwargs, max_retries=0)
        from httpx import ConnectTimeout
        from openai import APITimeoutError

        request_options = self._build_request_options(request)
        request_options["stream"] = True
        events = None
        try:
            events = await self.stream_client.responses.create(**request_options)
            async for event in events:
                if event.type == "response.output_text.delta":
                    yield TextDeltaEvent(
                        delta=event.delta,
                    )
                elif event.type == "response.completed":
                    openai_response = event.response
                    reason, error, incomplete_details = self.derive_end_reason(
                        openai_response
                    )
                    yield UsageEvent(
                        usage=ModelUsage(
                            input_tokens=openai_response.usage.input_tokens,
                            input_tokens_details=InputTokensDetails(
                                cached_tokens=openai_response.usage.input_tokens_details.cached_tokens,
                                cache_write_tokens=openai_response.usage.input_tokens_details.cache_write_tokens,
                            ),
                            output_tokens=openai_response.usage.output_tokens,
                            output_tokens_details=OutputTokensDetails(
                                reasoning_tokens=openai_response.usage.output_tokens_details.reasoning_tokens,
                            ),
                            total_tokens=openai_response.usage.total_tokens,
                        ),
                    )
                    yield EndEvent(
                        reason=reason,
                        error=error,
                        incomplete_details=incomplete_details,
                    )
                elif (
                    event.type == "response.incomplete"
                    or event.type == "response.failed"
                ):
                    openai_response = event.response
                    reason, error, incomplete_details = self.derive_end_reason(
                        openai_response
                    )
                    yield EndEvent(
                        reason=reason,
                        error=error,
                        incomplete_details=incomplete_details,
                    )
                else:
                    logger.warning("Unsupported stream event ignored.")
        except APITimeoutError as e:
            if isinstance(e.__cause__, ConnectTimeout):
                yield EndEvent(
                    reason=ModelResponseEndReason.CONNECTION_TIMEOUT,
                    error=ModelResponseError(
                        code=ModelResponseEndReason.CONNECTION_TIMEOUT,
                        message=e.message,
                    ),
                    incomplete_details=None,
                )
            elif isinstance(e.__cause__, ReadTimeout):
                yield EndEvent(
                    reason=ModelResponseEndReason.READ_TIMEOUT,
                    error=ModelResponseError(
                        code=ModelResponseEndReason.READ_TIMEOUT,
                        message=e.message,
                    ),
                    incomplete_details=None,
                )
            else:
                raise
        except APIStatusError as e:
            if e.status_code == 429:
                retry_after = self._parse_retry_after(
                    e.response.headers.get("Retry-After")
                )
                yield EndEvent(
                    reason=ModelResponseEndReason.RATE_LIMITED,
                    error=ModelResponseError(
                        code=ModelResponseEndReason.RATE_LIMITED,
                        message=e.message,
                        retry_after_seconds=retry_after,
                    ),
                    incomplete_details=None,
                )
            elif e.status_code == 503:
                retry_after = self._parse_retry_after(
                    e.response.headers.get("Retry-After")
                )
                yield EndEvent(
                    reason=ModelResponseEndReason.SERVICE_UNAVAILABLE,
                    error=ModelResponseError(
                        code=ModelResponseEndReason.SERVICE_UNAVAILABLE,
                        message=e.message,
                        retry_after_seconds=retry_after,
                    ),
                    incomplete_details=None,
                )
            elif e.status_code == 401:
                yield EndEvent(
                    reason=ModelResponseEndReason.AUTHENTICATION_FAILED,
                    error=ModelResponseError(
                        code=ModelResponseEndReason.AUTHENTICATION_FAILED,
                        message=e.message,
                    ),
                    incomplete_details=None,
                )
            elif e.status_code == 403:
                yield EndEvent(
                    reason=ModelResponseEndReason.PERMISSION_DENIED,
                    error=ModelResponseError(
                        code=ModelResponseEndReason.PERMISSION_DENIED,
                        message=e.message,
                    ),
                    incomplete_details=None,
                )
            elif e.status_code == 400 or e.status_code == 422:
                yield EndEvent(
                    reason=ModelResponseEndReason.INVALID_REQUEST,
                    error=ModelResponseError(
                        code=ModelResponseEndReason.INVALID_REQUEST,
                        message=e.message,
                    ),
                    incomplete_details=None,
                )
            else:
                raise
        except APIConnectionError as e:
            yield EndEvent(
                reason=ModelResponseEndReason.CONNECTION_FAILED,
                error=ModelResponseError(
                    code=ModelResponseEndReason.CONNECTION_FAILED,
                    message=e.message,
                ),
                incomplete_details=None,
            )
        except ReadTimeout:
            yield EndEvent(
                reason=ModelResponseEndReason.READ_TIMEOUT,
                error=ModelResponseError(
                    code=ModelResponseEndReason.READ_TIMEOUT,
                    message="Timed out while reading from the model service.",
                ),
                incomplete_details=None,
            )
        finally:
            if events is not None:
                await events.close()

    async def aclose(self) -> None:
        if self.stream_client is not None:
            await self.stream_client.close()
        if self.client is not None:
            self.client.close()

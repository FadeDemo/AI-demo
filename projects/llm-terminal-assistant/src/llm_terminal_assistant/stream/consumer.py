from asyncio import timeout
from collections.abc import AsyncGenerator, Callable

from llm_terminal_assistant.config import RequestTimeoutConfig
from llm_terminal_assistant.model import (
    ModelResponse,
    ModelResponseEndReason,
    ModelResponseError,
)
from llm_terminal_assistant.stream.events import (
    EndEvent,
    StreamEvent,
    TextDeltaEvent,
    UsageEvent,
)
from llm_terminal_assistant.stream.timing import StreamResponseTiming

_TIMEOUT_MESSAGES = {
    ModelResponseEndReason.FIRST_EVENT_TIMEOUT: "Timed out waiting for the first stream event.",
    ModelResponseEndReason.STREAM_IDLE_TIMEOUT: "Timed out waiting for the next stream event.",
    ModelResponseEndReason.REQUEST_DEADLINE_EXCEEDED: "The overall request deadline was exceeded.",
}


async def consume_stream(
    stream: AsyncGenerator[StreamEvent],
    consumer: Callable[[str], None],
    start_at: float,
    clock: Callable[[], float],
    request_timeout_config: RequestTimeoutConfig | None = None,
) -> ModelResponse:
    text_part = []
    usage = None
    reason = None
    error = None
    incomplete_details = None
    ttft_seconds = None
    last_event_at: float | None = None
    deadline_at = (
        start_at + request_timeout_config.request_deadline_seconds
        if request_timeout_config is not None
        else None
    )
    try:
        while True:
            remaining = None
            timeout_reason = None
            try:
                if request_timeout_config is not None:
                    now = clock()
                    if last_event_at is None:
                        remaining = request_timeout_config.first_event_seconds
                        timeout_reason = ModelResponseEndReason.FIRST_EVENT_TIMEOUT
                    else:
                        remaining = (
                            last_event_at
                            + request_timeout_config.stream_idle_seconds
                            - now
                        )
                        timeout_reason = ModelResponseEndReason.STREAM_IDLE_TIMEOUT
                    total_remaining = deadline_at - now
                    if total_remaining <= remaining:
                        remaining = total_remaining
                        timeout_reason = (
                            ModelResponseEndReason.REQUEST_DEADLINE_EXCEEDED
                        )
                    if remaining <= 0:
                        raise TimeoutError
                async with timeout(remaining):
                    event = await anext(stream)
                last_event_at = clock()
            except TimeoutError as e:
                if timeout_reason is None:
                    raise ValueError(
                        f"Unsupported timeout reason: {timeout_reason}"
                    ) from e
                reason = timeout_reason
                error = ModelResponseError(
                    code=reason,
                    message=_TIMEOUT_MESSAGES[reason],
                )
                break
            except StopAsyncIteration:
                break
            except Exception:
                reason = ModelResponseEndReason.STREAM_READ_FAILED
                error = ModelResponseError(
                    code=ModelResponseEndReason.STREAM_READ_FAILED,
                    message="Streaming response could not be read. The answer may be incomplete.",
                )
                break
            if isinstance(event, TextDeltaEvent):
                if ttft_seconds is None and event.delta:
                    ttft_seconds = clock() - start_at
                consumer(event.delta)
                text_part.append(event.delta)
            elif isinstance(event, UsageEvent):
                usage = event.usage
            elif isinstance(event, EndEvent):
                reason = event.reason
                error = event.error
                incomplete_details = event.incomplete_details
                break
            else:
                raise ValueError(f"Unsupported event type: {type(event)}")
    finally:
        await stream.aclose()
    total_seconds = clock() - start_at
    text = "".join(text_part)
    if reason is None:
        reason = ModelResponseEndReason.MISSING_END_EVENT
    return ModelResponse(
        text=text,
        reason=reason,
        usage=usage,
        error=error,
        incomplete_details=incomplete_details,
        timing=StreamResponseTiming(
            total_seconds=total_seconds,
            ttft_seconds=ttft_seconds,
        ),
    )

from collections.abc import AsyncGenerator, Callable

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


async def consume_stream(
    stream: AsyncGenerator[StreamEvent],
    consumer: Callable[[str], None],
    start_at: float,
    clock: Callable[[], float],
) -> ModelResponse:
    text_part = []
    usage = None
    reason = None
    error = None
    incomplete_details = None
    ttft_seconds = None
    try:
        while True:
            try:
                event = await anext(stream)
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

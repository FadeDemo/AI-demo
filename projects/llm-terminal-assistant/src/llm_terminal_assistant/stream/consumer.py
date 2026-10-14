from collections.abc import Callable, Generator

from llm_terminal_assistant.model import ModelResponse, ModelResponseEndReason
from llm_terminal_assistant.stream.events import (
    EndEvent,
    StreamEvent,
    TextDeltaEvent,
    UsageEvent,
)


def consume_stream(
    stream: Generator[StreamEvent], consumer: Callable[[str], None]
) -> ModelResponse:
    text_part = []
    usage = None
    reason = None
    error = None
    incomplete_details = None
    try:
        for event in stream:
            if isinstance(event, TextDeltaEvent):
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
        stream.close()
    text = "".join(text_part)
    if reason is None:
        reason = ModelResponseEndReason.MISSING_END_EVENT
    return ModelResponse(
        text=text,
        reason=reason,
        usage=usage,
        error=error,
        incomplete_details=incomplete_details,
    )

from dataclasses import dataclass

from llm_terminal_assistant.model import (
    ModelResponseEndReason,
    ModelResponseError,
    ModelResponseIncompleteDetails,
    ModelUsage,
)


@dataclass
class TextDeltaEvent:
    delta: str


@dataclass
class UsageEvent:
    usage: ModelUsage


@dataclass
class EndEvent:
    reason: ModelResponseEndReason
    error: ModelResponseError | None
    incomplete_details: ModelResponseIncompleteDetails | None


type StreamEvent = TextDeltaEvent | UsageEvent | EndEvent

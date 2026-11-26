from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from llm_shared.message import Message
from llm_shared.tools.definition import ToolDefinition
from llm_shared.tools.protocol import ToolCallRequest, ToolCallResult


@dataclass
class ModelOutputFormat:
    type: Literal["text", "json_schema", "json_object"] = "text"
    name: str | None = None
    schema: dict[str, object] | None = None


type ModelInputItem = Message | ToolCallRequest | ToolCallResult


@dataclass
class ModelRequest:
    input: list[ModelInputItem]
    reserved_output_tokens: int
    output_format: ModelOutputFormat | None = None
    reasoning_effort: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    tools: list[ToolDefinition] = field(default_factory=list)


@dataclass
class ModelUsage:
    input_tokens: int
    input_tokens_details: InputTokensDetails
    output_tokens: int
    output_tokens_details: OutputTokensDetails
    total_tokens: int


@dataclass
class InputTokensDetails:
    cached_tokens: int
    cache_write_tokens: int


@dataclass
class OutputTokensDetails:
    reasoning_tokens: int


class ModelResponseEndReason(StrEnum):
    COMPLETED_NORMALLY = "completed_normally"
    REQUEST_FAILED = "request_failed"
    REQUEST_CANCELLED = "request_cancelled"
    REQUEST_INCOMPLETE = "request_incomplete"
    MISSING_END_EVENT = "missing_end_event"
    STREAM_READ_FAILED = "stream_read_failed"
    CONNECTION_TIMEOUT = "connection_timeout"
    FIRST_EVENT_TIMEOUT = "first_event_timeout"
    STREAM_IDLE_TIMEOUT = "stream_idle_timeout"
    REQUEST_DEADLINE_EXCEEDED = "request_deadline_exceeded"
    RATE_LIMITED = "rate_limited"
    SERVICE_UNAVAILABLE = "service_unavailable"
    AUTHENTICATION_FAILED = "authentication_failed"
    PERMISSION_DENIED = "permission_denied"
    INVALID_REQUEST = "invalid_request"
    CONNECTION_FAILED = "connection_failed"
    READ_TIMEOUT = "read_timeout"
    INSUFFICIENT_RETRY_TIME = "insufficient_retry_time"


@dataclass
class ModelResponseError:
    code: str
    message: str
    retry_after_seconds: float | None = None


@dataclass
class ModelResponseIncompleteDetails:
    reason: Literal["max_output_tokens", "content_filter"]

import asyncio
from collections.abc import Awaitable, Callable
from random import uniform

from llm_terminal_assistant.config import RequestRetryConfig
from llm_terminal_assistant.model import ModelResponse, ModelResponseEndReason
from llm_terminal_assistant.request_control import (
    RequestStoppedError,
    RequestStopReason,
    check_request_deadline,
)


def calculate_retry_delay(
    config: RequestRetryConfig,
    retry_attempt: int,
    parsed_retry_after: float | None,
    uniform: Callable[[float, float], float] = uniform,
) -> float:
    upper_bound = min(
        config.base_delay_seconds * (2 ** (retry_attempt - 1)), config.max_delay_seconds
    )
    calculated_delay = uniform(0, upper_bound)
    if parsed_retry_after is not None:
        return max(calculated_delay, parsed_retry_after)
    return calculated_delay


def can_retry_response(
    response: ModelResponse, retry_attempt: int, config: RequestRetryConfig
) -> bool:
    return (
        retry_attempt < config.max_attempts
        and response.text == ""
        and response.reason
        in (
            ModelResponseEndReason.CONNECTION_FAILED,
            ModelResponseEndReason.CONNECTION_TIMEOUT,
            ModelResponseEndReason.READ_TIMEOUT,
            ModelResponseEndReason.FIRST_EVENT_TIMEOUT,
            ModelResponseEndReason.STREAM_IDLE_TIMEOUT,
            ModelResponseEndReason.RATE_LIMITED,
            ModelResponseEndReason.SERVICE_UNAVAILABLE,
        )
    )


async def wait_before_retry(
    retry_delay: float,
    deadline_at: float | None,
    clock: Callable[[], float],
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    now = clock()
    remaining = deadline_at - now if deadline_at is not None else None
    if remaining is not None and remaining <= 0:
        raise RequestStoppedError(RequestStopReason.REQUEST_DEADLINE_EXCEEDED)
    if remaining is not None and remaining <= retry_delay:
        raise RequestStoppedError(RequestStopReason.INSUFFICIENT_RETRY_TIME)
    try:
        async with asyncio.timeout(remaining):
            await sleep(retry_delay)
            check_request_deadline(deadline_at=deadline_at, clock=clock)
    except TimeoutError as e:
        raise RequestStoppedError(RequestStopReason.REQUEST_DEADLINE_EXCEEDED) from e
    except asyncio.CancelledError:
        raise

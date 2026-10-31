"""单轮请求的关联、用量累计和最终摘要，仅输出诊断元数据。"""

import asyncio
import hashlib
import logging
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from llm_terminal_assistant.budgeter import BudgetRejectedError
from llm_terminal_assistant.model import ModelResponse
from llm_terminal_assistant.request_control import RequestStoppedError
from llm_terminal_assistant.tools.errors import ToolLoopStoppedError


@dataclass
class RequestObservation:
    request_id: str
    entry: str
    model: str
    prompt_version: str
    start_at: float
    model_calls: int = 0
    usage_calls: int = 0
    known_input_tokens: int = 0
    known_output_tokens: int = 0
    known_total_tokens: int = 0
    reason: str = "application_failed"
    ttft_seconds: float | None = None

    def begin_model_call(self) -> int:
        self.model_calls += 1
        return self.model_calls

    def log_model_call(
        self,
        logger: logging.Logger,
        response: ModelResponse | None,
        *,
        attempt: int | None = None,
        failure_reason: str = "model_call_failed",
    ) -> None:
        usage = response.usage if response is not None else None
        reason = response.reason if response is not None else failure_reason
        if usage is not None:
            self.usage_calls += 1
            self.known_input_tokens += usage.input_tokens
            self.known_output_tokens += usage.output_tokens
            self.known_total_tokens += usage.total_tokens
        fields = {
            "event": "model_call",
            "request_id": self.request_id,
            "model_call_index": self.model_calls,
            "reason": reason,
            "input_tokens": usage.input_tokens if usage is not None else None,
            "output_tokens": usage.output_tokens if usage is not None else None,
            "total_tokens": usage.total_tokens if usage is not None else None,
        }
        if attempt is not None:
            logger.info(
                "Attempt finished: request_id=%s, attempt=%s, reason=%s, "
                "input_tokens=%s, output_tokens=%s, total_tokens=%s, model_call_index=%s",
                self.request_id,
                attempt,
                reason,
                fields["input_tokens"],
                fields["output_tokens"],
                fields["total_tokens"],
                self.model_calls,
                extra={**fields, "attempt": attempt},
            )
        elif response is None:
            logger.error(
                "ModelRequest[%s]: Model call %d failed. Error is model_call_failed. "
                "Input tokens are none, output tokens are none, total tokens are none.",
                self.request_id,
                self.model_calls,
                extra=fields,
            )
        else:
            logger.info(
                "ModelRequest[%s]: Model call %d finished. End reason is %s. "
                "Input tokens are %s, output tokens are %s, total tokens are %s.",
                self.request_id,
                self.model_calls,
                reason,
                fields["input_tokens"],
                fields["output_tokens"],
                fields["total_tokens"],
                extra=fields,
            )

    def log_summary(self, logger: logging.Logger, total_seconds: float) -> None:
        status = {
            "completed_normally": "success",
            "request_cancelled": "cancelled",
            "request_incomplete": "incomplete",
        }.get(self.reason, "failed")
        ttft_status = (
            "not_applicable"
            if self.entry == "tools"
            else "missing"
            if self.ttft_seconds is None
            else "observed"
        )
        has_usage = self.usage_calls > 0 or self.model_calls == 0
        fields = {
            "request_id": self.request_id,
            "attempts": self.model_calls if self.entry == "stream" else None,
            "reason": self.reason,
            "ttft_seconds": self.ttft_seconds,
            "total_seconds": total_seconds,
            "entry": self.entry,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "status": status,
            "model_calls": self.model_calls,
            "retries": max(0, self.model_calls - 1) if self.entry == "stream" else 0,
            "ttft_status": ttft_status,
            "input_tokens": self.known_input_tokens if has_usage else None,
            "output_tokens": self.known_output_tokens if has_usage else None,
            "total_tokens": self.known_total_tokens if has_usage else None,
            "usage_complete": self.usage_calls == self.model_calls,
            "unknown_usage_calls": self.model_calls - self.usage_calls,
        }
        logger.info(
            "Request finished: " + ", ".join(f"{key}=%s" for key in fields),
            *fields.values(),
            extra={"event": "request_summary", **fields},
        )


@contextmanager
def observe_request(
    logger: logging.Logger,
    *,
    entry: str,
    model: str,
    system_prompt: str,
    clock: Callable[[], float],
) -> Iterator[RequestObservation]:
    observation = RequestObservation(
        start_at=clock(),
        request_id=uuid.uuid4().hex,
        entry=entry,
        model=model if isinstance(model, str) else "unknown",
        prompt_version="sha256:" + hashlib.sha256(system_prompt.encode()).hexdigest(),
    )
    try:
        yield observation
    except (BudgetRejectedError, RequestStoppedError, ToolLoopStoppedError) as error:
        observation.reason = error.reason.value
        raise
    except asyncio.CancelledError:
        observation.reason = "request_cancelled"
        raise
    finally:
        observation.log_summary(logger, clock() - observation.start_at)

from dataclasses import dataclass
from enum import StrEnum

from llm_terminal_assistant.model import ModelLimits, ModelRequest
from llm_terminal_assistant.request_encoder import RequestEncoder
from llm_terminal_assistant.token_counter import TokenCounter


class BudgetRejectionReason(StrEnum):
    NEGATIVE_LIMIT = "negative_limit"
    MAX_INPUT_EXCEEDED = "max_input_exceeded"
    MAX_OUTPUT_EXCEEDED = "max_output_exceeded"
    CONTEXT_WINDOW_EXCEEDED = "context_window_exceeded"


@dataclass
class BudgetResult:
    estimated_input_tokens: int
    reserved_output_tokens: int
    safety_margin_tokens: int
    remaining_tokens: int


class BudgetRejectedError(Exception):
    def __init__(self, reason: BudgetRejectionReason):
        super().__init__(f"Budget rejected: {reason}")
        self.reason = reason


class Budgeter:
    def __init__(
        self,
        token_counter: TokenCounter,
        model_limits: ModelLimits,
        safety_margin_tokens: int,
        request_encoder: RequestEncoder,
    ):
        self.token_counter = token_counter
        self.model_limits = model_limits
        self.safety_margin_tokens = safety_margin_tokens
        self.request_encoder = request_encoder

    def check(self, request: ModelRequest) -> BudgetResult:
        if (
            self.model_limits.context_window_tokens < 0
            or request.reserved_output_tokens < 0
            or self.safety_margin_tokens < 0
            or (
                self.model_limits.max_input_tokens is not None
                and self.model_limits.max_input_tokens < 0
            )
            or (
                self.model_limits.max_output_tokens is not None
                and self.model_limits.max_output_tokens < 0
            )
        ):
            raise BudgetRejectedError(BudgetRejectionReason.NEGATIVE_LIMIT)

        encoded_request = self.request_encoder.encode_request(request)
        estimated_input_tokens = self.token_counter.count_tokens(encoded_request)

        if (
            self.model_limits.max_input_tokens is not None
            and estimated_input_tokens > self.model_limits.max_input_tokens
        ):
            raise BudgetRejectedError(BudgetRejectionReason.MAX_INPUT_EXCEEDED)

        if (
            self.model_limits.max_output_tokens is not None
            and request.reserved_output_tokens > self.model_limits.max_output_tokens
        ):
            raise BudgetRejectedError(BudgetRejectionReason.MAX_OUTPUT_EXCEEDED)

        remaining_tokens = (
            self.model_limits.context_window_tokens
            - estimated_input_tokens
            - request.reserved_output_tokens
            - self.safety_margin_tokens
        )
        if remaining_tokens < 0:
            raise BudgetRejectedError(BudgetRejectionReason.CONTEXT_WINDOW_EXCEEDED)

        return BudgetResult(
            estimated_input_tokens=estimated_input_tokens,
            reserved_output_tokens=request.reserved_output_tokens,
            safety_margin_tokens=self.safety_margin_tokens,
            remaining_tokens=remaining_tokens,
        )

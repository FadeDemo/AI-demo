from collections import deque

from llm_terminal_assistant.client import ModelClient
from llm_terminal_assistant.config import ModelConfig
from llm_terminal_assistant.model import (
    InputTokensDetails,
    ModelRequest,
    ModelResponse,
    ModelResponseEndReason,
    ModelResponseIncompleteDetails,
    ModelUsage,
    OutputTokensDetails,
)


class FakeClient(ModelClient):
    def __init__(
        self,
        config: ModelConfig,
        outcome: str = "normal",
        *,
        scripted_responses: list[ModelResponse] | None = None,
    ):
        super().__init__(config)
        self.outcome = outcome
        self.scripted_responses = (
            deque(scripted_responses) if scripted_responses is not None else None
        )
        self.requests: list[ModelRequest] = []

    def send(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if self.scripted_responses is not None:
            if not self.scripted_responses:
                raise RuntimeError("No more scripted responses available")
            return self.scripted_responses.popleft()
        construction_options = {
            "text": "This is a fake response",
            "usage": ModelUsage(
                input_tokens=20,
                output_tokens=20,
                input_tokens_details=InputTokensDetails(
                    cached_tokens=10, cache_write_tokens=10
                ),
                output_tokens_details=OutputTokensDetails(reasoning_tokens=20),
                total_tokens=40,
            ),
        }
        if self.outcome == "normal":
            construction_options["reason"] = ModelResponseEndReason.COMPLETED_NORMALLY
        elif self.outcome == "max_output_tokens":
            construction_options["reason"] = ModelResponseEndReason.REQUEST_INCOMPLETE
            construction_options["incomplete_details"] = ModelResponseIncompleteDetails(
                reason="max_output_tokens"
            )
        return ModelResponse(**construction_options)

    def validate_reasoning_effort(
        self, effort: str | None, allowed_efforts: tuple[str, ...]
    ) -> None:
        if effort is not None and effort not in allowed_efforts:
            raise ValueError(
                f"Reasoning effort '{effort}' is not supported for this model. "
                f"Supported efforts: {allowed_efforts}"
            )

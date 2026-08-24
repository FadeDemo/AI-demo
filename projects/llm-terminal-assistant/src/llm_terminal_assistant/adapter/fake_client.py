from llm_terminal_assistant.client import ModelClient
from llm_terminal_assistant.model import (
    InputTokensDetails,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    OutputTokensDetails,
)


class FakeClient(ModelClient):
    def send(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            text="This is a fake response",
            reason="Completed normally",
            usage=ModelUsage(
                input_tokens=20,
                output_tokens=20,
                input_tokens_details=InputTokensDetails(
                    cached_tokens=10, cache_write_tokens=10
                ),
                output_tokens_details=OutputTokensDetails(reasoning_tokens=20),
                total_tokens=40,
            ),
        )

    def validate_reasoning_effort(
        self, effort: str | None, allowed_efforts: tuple[str, ...]
    ) -> None:
        if effort is not None and effort not in allowed_efforts:
            raise ValueError(
                f"Reasoning effort '{effort}' is not supported for this model. "
                f"Supported efforts: {allowed_efforts}"
            )

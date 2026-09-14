import unittest
from datetime import UTC, datetime

from llm_terminal_assistant.config import ModelConfig
from llm_terminal_assistant.model import (
    DEEPSEEK_V41_FLASH,
    InputTokensDetails,
    ModelRequest,
    ModelResponse,
    ModelResponseEndReason,
    ModelResponseIncompleteDetails,
    ModelUsage,
    OutputTokensDetails,
)
from llm_terminal_assistant.sampling_experiment import (
    ExperimentInput,
    run_experiment,
    validate_experiment_settings,
)


class RecordingClient:
    def __init__(self):
        self.requests: list[ModelRequest] = []

    def send(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(
            text=f"response-{len(self.requests)}",
            reason=ModelResponseEndReason.COMPLETED_NORMALLY,
            usage=ModelUsage(
                input_tokens=10,
                input_tokens_details=InputTokensDetails(
                    cached_tokens=0,
                    cache_write_tokens=0,
                ),
                output_tokens=5,
                output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
                total_tokens=15,
            ),
        )


def build_inputs() -> list[ExperimentInput]:
    return [
        ExperimentInput(input_id=f"input-{index:02d}", prompt=f"prompt {index}")
        for index in range(1, 11)
    ]


def build_config() -> ModelConfig:
    return ModelConfig(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="deepseek-flash",
        model_profile=DEEPSEEK_V41_FLASH,
        provider="openai",
        reasoning_effort="low",
        top_p=0.9,
    )


class SamplingExperimentTests(unittest.TestCase):
    def test_runs_sixty_independent_requests_and_records_full_settings(self):
        client = RecordingClient()
        records = []

        summary = run_experiment(
            client=client,
            config=build_config(),
            inputs=build_inputs(),
            parameter="temperature",
            values=[0.2, 0.8, 1.4],
            runs=2,
            max_output_tokens=256,
            system_prompt="fixed system prompt",
            write_record=records.append,
            experiment_id="experiment-1",
            timestamp_factory=lambda: datetime(2026, 8, 26, tzinfo=UTC),
        )

        self.assertEqual(summary.attempted, 60)
        self.assertEqual(summary.succeeded, 60)
        self.assertEqual(summary.failed, 0)
        self.assertEqual(len(client.requests), 60)
        self.assertEqual(len(records), 60)
        self.assertEqual(
            {
                (record["run"], record["parameter_value"], record["input_id"])
                for record in records
            },
            {
                (run, value, f"input-{input_index:02d}")
                for run in (1, 2)
                for value in (0.2, 0.8, 1.4)
                for input_index in range(1, 11)
            },
        )
        for request in client.requests:
            self.assertEqual(len(request.messages), 2)
            self.assertEqual(
                [message.role for message in request.messages], ["system", "user"]
            )
            self.assertEqual(request.top_p, 0.9)
            self.assertEqual(request.reserved_output_tokens, 256)
        for record in records:
            self.assertEqual(record["experiment_id"], "experiment-1")
            self.assertEqual(record["parameters"]["top_p"], 0.9)
            self.assertEqual(record["judgement"]["status"], "pending")
            self.assertEqual(record["status"], "succeeded")

    def test_records_a_failure_and_continues(self):
        class FailingOnceClient(RecordingClient):
            def send(self, request: ModelRequest) -> ModelResponse:
                if not self.requests:
                    self.requests.append(request)
                    raise RuntimeError("temporary failure")
                return super().send(request)

        client = FailingOnceClient()
        records = []

        summary = run_experiment(
            client=client,
            config=build_config(),
            inputs=build_inputs(),
            parameter="top_p",
            values=[0.2, 0.6, 1.0],
            runs=2,
            max_output_tokens=128,
            system_prompt="fixed",
            write_record=records.append,
        )

        self.assertEqual(summary.attempted, 60)
        self.assertEqual(summary.succeeded, 59)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(records[0]["status"], "failed")
        self.assertEqual(records[0]["error_type"], "RuntimeError")
        self.assertEqual(records[1]["status"], "succeeded")

    def test_counts_an_incomplete_response_as_a_failure(self):
        class IncompleteOnceClient(RecordingClient):
            def send(self, request: ModelRequest) -> ModelResponse:
                response = super().send(request)
                if len(self.requests) == 1:
                    response.reason = ModelResponseEndReason.REQUEST_INCOMPLETE
                    response.incomplete_details = ModelResponseIncompleteDetails(
                        reason="max_output_tokens"
                    )
                    response.text = ""
                return response

        client = IncompleteOnceClient()
        records = []

        summary = run_experiment(
            client=client,
            config=build_config(),
            inputs=build_inputs(),
            parameter="temperature",
            values=[0.2, 0.8, 1.4],
            runs=2,
            max_output_tokens=128,
            system_prompt="fixed",
            write_record=records.append,
        )

        self.assertEqual(summary.attempted, 60)
        self.assertEqual(summary.succeeded, 59)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(records[0]["status"], "incomplete")
        self.assertEqual(
            records[0]["finish_reason"],
            ModelResponseEndReason.REQUEST_INCOMPLETE,
        )
        self.assertEqual(records[1]["status"], "succeeded")

    def test_rejects_settings_that_do_not_meet_course_minimums(self):
        with self.assertRaisesRegex(ValueError, "three distinct"):
            validate_experiment_settings(
                config=build_config(),
                parameter="temperature",
                values=[0.2, 0.2, 0.8],
                runs=2,
                max_output_tokens=128,
            )
        with self.assertRaisesRegex(ValueError, "At least two"):
            validate_experiment_settings(
                config=build_config(),
                parameter="temperature",
                values=[0.2, 0.8, 1.4],
                runs=1,
                max_output_tokens=128,
            )


if __name__ == "__main__":
    unittest.main()

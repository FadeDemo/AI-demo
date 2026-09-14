import unittest
from dataclasses import replace
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
from llm_terminal_assistant.prompt_experiment import (
    DEFAULT_EVALUATION_PATH,
    DEFAULT_PROMPTS_PATH,
    build_messages,
    load_evaluation_samples,
    load_prompt_definition,
    run_experiment,
    validate_example_independence,
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
                input_tokens=100 + len(self.requests),
                input_tokens_details=InputTokensDetails(
                    cached_tokens=0,
                    cache_write_tokens=0,
                ),
                output_tokens=20,
                output_tokens_details=OutputTokensDetails(reasoning_tokens=5),
                total_tokens=120 + len(self.requests),
            ),
        )


def build_config() -> ModelConfig:
    return ModelConfig(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="deepseek-flash",
        model_profile=DEEPSEEK_V41_FLASH,
        provider="openai",
        reasoning_effort="low",
        temperature=0.2,
    )


class PromptExperimentTests(unittest.TestCase):
    def setUp(self):
        self.samples = load_evaluation_samples(DEFAULT_EVALUATION_PATH)
        self.definition = load_prompt_definition(DEFAULT_PROMPTS_PATH)

    def test_loads_fixed_evaluation_and_two_prompt_versions(self):
        self.assertEqual(len(self.samples), 12)
        self.assertEqual(len({sample.sample_id for sample in self.samples}), 12)
        self.assertEqual(
            {version.version_id for version in self.definition.versions},
            {"zero-shot", "few-shot"},
        )
        versions = {version.version_id: version for version in self.definition.versions}
        self.assertEqual(versions["zero-shot"].examples, ())
        self.assertEqual(len(versions["few-shot"].examples), 3)

    def test_builds_zero_shot_and_few_shot_messages_without_evaluation_metadata(self):
        versions = {version.version_id: version for version in self.definition.versions}
        sample = self.samples[0]

        zero_shot_messages = build_messages(
            self.definition, versions["zero-shot"], sample
        )
        few_shot_messages = build_messages(
            self.definition, versions["few-shot"], sample
        )

        self.assertEqual(
            [message.role for message in zero_shot_messages], ["system", "user"]
        )
        self.assertEqual(
            [message.role for message in few_shot_messages],
            [
                "system",
                "user",
                "assistant",
                "user",
                "assistant",
                "user",
                "assistant",
                "user",
            ],
        )
        self.assertEqual(
            zero_shot_messages[-1].content,
            f"<source>\n{sample.source}\n</source>",
        )
        self.assertEqual(few_shot_messages[-1].content, zero_shot_messages[-1].content)
        for messages in (zero_shot_messages, few_shot_messages):
            rendered_context = "\n".join(message.content for message in messages)
            self.assertNotIn(sample.sample_id, rendered_context)
            for expectation in sample.expected_behaviors:
                self.assertNotIn(expectation, rendered_context)

    def test_runs_twenty_four_independent_requests_and_records_pending_checks(self):
        client = RecordingClient()
        records = []

        summary = run_experiment(
            client=client,
            config=build_config(),
            samples=self.samples,
            definition=self.definition,
            max_output_tokens=16_384,
            write_record=records.append,
            experiment_id="prompt-experiment-1",
            timestamp_factory=lambda: datetime(2026, 8, 31, tzinfo=UTC),
        )

        self.assertEqual(summary.attempted, 24)
        self.assertEqual(summary.succeeded, 24)
        self.assertEqual(summary.failed, 0)
        self.assertEqual(len(client.requests), 24)
        self.assertEqual(len(records), 24)
        self.assertEqual(
            {(record["prompt_version"], record["sample_id"]) for record in records},
            {
                (version_id, sample.sample_id)
                for version_id in ("zero-shot", "few-shot")
                for sample in self.samples
            },
        )

        samples_by_id = {sample.sample_id: sample for sample in self.samples}
        for request, record in zip(client.requests, records, strict=True):
            sample = samples_by_id[record["sample_id"]]
            self.assertEqual(request.temperature, 0.2)
            self.assertIsNone(request.top_p)
            self.assertEqual(request.reserved_output_tokens, 16_384)
            self.assertEqual(record["experiment_id"], "prompt-experiment-1")
            self.assertEqual(record["status"], "succeeded")
            self.assertEqual(record["usage"]["input_tokens"] >= 101, True)
            self.assertEqual(record["judgement"]["status"], "pending")
            self.assertEqual(
                [check["expectation"] for check in record["judgement"]["checks"]],
                list(sample.expected_behaviors),
            )
            self.assertTrue(
                all(
                    check["status"] == "pending"
                    for check in record["judgement"]["checks"]
                )
            )
            expected_message_count = 2 if record["prompt_version"] == "zero-shot" else 8
            self.assertEqual(len(request.messages), expected_message_count)
            self.assertEqual(record["messages"][-1]["role"], "user")

    def test_records_a_request_failure_as_not_evaluated_and_continues(self):
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
            samples=self.samples,
            definition=self.definition,
            max_output_tokens=512,
            write_record=records.append,
        )

        self.assertEqual(summary.attempted, 24)
        self.assertEqual(summary.succeeded, 23)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(len(records), 24)
        self.assertEqual(records[0]["status"], "failed")
        self.assertEqual(records[0]["judgement"]["status"], "not_evaluated")
        self.assertEqual(records[1]["status"], "succeeded")

    def test_counts_an_incomplete_response_as_a_failed_request(self):
        class IncompleteOnceClient(RecordingClient):
            def send(self, request: ModelRequest) -> ModelResponse:
                response = super().send(request)
                if len(self.requests) == 1:
                    response.reason = ModelResponseEndReason.REQUEST_INCOMPLETE
                    response.incomplete_details = ModelResponseIncompleteDetails(
                        reason="max_output_tokens"
                    )
                return response

        records = []
        summary = run_experiment(
            client=IncompleteOnceClient(),
            config=build_config(),
            samples=self.samples,
            definition=self.definition,
            max_output_tokens=512,
            write_record=records.append,
        )

        self.assertEqual(summary.succeeded, 23)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(records[0]["status"], "incomplete")
        self.assertEqual(
            records[0]["incomplete_details"], {"reason": "max_output_tokens"}
        )
        self.assertEqual(records[0]["judgement"]["status"], "pending")

    def test_rejects_an_example_that_duplicates_an_evaluation_source(self):
        versions = {version.version_id: version for version in self.definition.versions}
        few_shot = versions["few-shot"]
        duplicate_example = replace(few_shot.examples[0], source=self.samples[0].source)
        invalid_few_shot = replace(
            few_shot,
            examples=(duplicate_example, *few_shot.examples[1:]),
        )
        invalid_definition = replace(
            self.definition,
            versions=tuple(
                invalid_few_shot if version.version_id == "few-shot" else version
                for version in self.definition.versions
            ),
        )

        with self.assertRaisesRegex(ValueError, "duplicates an evaluation source"):
            validate_example_independence(self.samples, invalid_definition)

    def test_rejects_fake_provider_and_invalid_output_budget(self):
        fake_config = replace(build_config(), provider="faked")
        with self.assertRaisesRegex(ValueError, "PROVIDER=openai"):
            validate_experiment_settings(
                config=fake_config,
                max_output_tokens=512,
            )
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            validate_experiment_settings(
                config=build_config(),
                max_output_tokens=0,
            )


if __name__ == "__main__":
    unittest.main()

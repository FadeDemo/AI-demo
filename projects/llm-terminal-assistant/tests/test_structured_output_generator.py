import json
import unittest

from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import (
    InputTokensDetails,
    ModelRequest,
    ModelResponse,
    ModelResponseEndReason,
    ModelResponseIncompleteDetails,
    ModelUsage,
    OutputTokensDetails,
)
from llm_terminal_assistant.structured_output.errors import (
    ErrorCategory,
    StructuredOutputError,
)
from llm_terminal_assistant.structured_output.generator import (
    REPAIR_INSTRUCTION,
    generate_study_card,
)
from llm_terminal_assistant.structured_output.study_card import StudyCard


class ScriptedModelClient:
    """按顺序返回预设响应，并记录生成器发出的每个请求。"""

    def __init__(self, responses: list[ModelResponse]):
        self.responses = responses
        self.requests: list[ModelRequest] = []

    def send(self, request: ModelRequest) -> ModelResponse:
        response_index = len(self.requests)
        self.requests.append(request)

        if response_index >= len(self.responses):
            raise AssertionError("Model client received an unexpected request.")

        return self.responses[response_index]


def model_usage() -> ModelUsage:
    return ModelUsage(
        input_tokens=0,
        input_tokens_details=InputTokensDetails(
            cached_tokens=0,
            cache_write_tokens=0,
        ),
        output_tokens=0,
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
        total_tokens=0,
    )


def completed_response(text: str) -> ModelResponse:
    return ModelResponse(
        text=text,
        reason=ModelResponseEndReason.COMPLETED_NORMALLY,
        usage=model_usage(),
    )


def valid_study_card() -> dict[str, object]:
    return {
        "title": "Structured output",
        "summary": "Applications validate model output before using it.",
        "questions": [
            "What does JSON parsing validate?",
            "What remains after Schema validation?",
        ],
        "source_ids": ["lesson-01"],
    }


def base_request() -> ModelRequest:
    return ModelRequest(
        messages=[
            Message(
                role="user",
                content="Create a study card from lesson-01.",
            )
        ],
        reserved_output_tokens=1_024,
    )


class StructuredOutputGeneratorTests(unittest.TestCase):
    def test_valid_first_response_calls_model_once(self):
        request = base_request()
        client = ScriptedModelClient(
            [completed_response(json.dumps(valid_study_card()))]
        )

        card = generate_study_card(
            client,
            request,
            {"lesson-01"},
            "request-valid-first-response",
        )

        self.assertEqual(card, StudyCard(**valid_study_card()))
        self.assertEqual(len(client.requests), 1)
        self.assertIsNone(request.output_format)
        self.assertEqual(len(request.messages), 1)

        output_format = client.requests[0].output_format
        self.assertIsNotNone(output_format)
        self.assertEqual(output_format.type, "json_schema")
        self.assertEqual(output_format.name, "study_card")
        self.assertIsNotNone(output_format.schema)

    def test_parse_failure_builds_one_repair_request(self):
        invalid_output = "not-json"
        client = ScriptedModelClient(
            [
                completed_response(invalid_output),
                completed_response(json.dumps(valid_study_card())),
            ]
        )

        with self.assertLogs(
            "llm_terminal_assistant.structured_output.pipeline",
            level="ERROR",
        ):
            card = generate_study_card(
                client,
                base_request(),
                {"lesson-01"},
                "request-repair-success",
            )

        self.assertEqual(card, StudyCard(**valid_study_card()))
        self.assertEqual(len(client.requests), 2)

        initial_request, repair_request = client.requests
        self.assertEqual(
            [message.role for message in repair_request.messages],
            ["user", "assistant", "user"],
        )
        self.assertEqual(repair_request.messages[-2].content, invalid_output)
        self.assertEqual(repair_request.messages[-1].content, REPAIR_INSTRUCTION)
        self.assertEqual(repair_request.output_format, initial_request.output_format)

    def test_second_parse_failure_stops_after_two_requests(self):
        client = ScriptedModelClient(
            [
                completed_response("first-invalid-output"),
                completed_response("second-invalid-output"),
            ]
        )

        with (
            self.assertLogs(
                "llm_terminal_assistant.structured_output.pipeline",
                level="ERROR",
            ),
            self.assertRaises(StructuredOutputError) as captured_error,
        ):
            generate_study_card(
                client,
                base_request(),
                {"lesson-01"},
                "request-repair-failed",
            )

        self.assertEqual(captured_error.exception.category, ErrorCategory.PARSE_ERROR)
        self.assertEqual(len(client.requests), 2)

    def test_non_repairable_validation_errors_do_not_retry(self):
        missing_title = valid_study_card()
        del missing_title["title"]

        invalid_source = valid_study_card()
        invalid_source["source_ids"] = ["lesson-02"]

        cases = (
            (
                missing_title,
                ErrorCategory.SCHEMA_VALIDATION_ERROR,
            ),
            (
                invalid_source,
                ErrorCategory.BUSINESS_RULE_VALIDATION_ERROR,
            ),
        )

        for output, expected_category in cases:
            with self.subTest(category=expected_category):
                client = ScriptedModelClient([completed_response(json.dumps(output))])

                with (
                    self.assertLogs(
                        "llm_terminal_assistant.structured_output.pipeline",
                        level="ERROR",
                    ),
                    self.assertRaises(StructuredOutputError) as captured_error,
                ):
                    generate_study_card(
                        client,
                        base_request(),
                        {"lesson-01"},
                        f"request-{expected_category}",
                    )

                self.assertEqual(
                    captured_error.exception.category,
                    expected_category,
                )
                self.assertEqual(len(client.requests), 1)

    def test_incomplete_response_does_not_enter_repair(self):
        client = ScriptedModelClient(
            [
                ModelResponse(
                    text='{"title": "truncated"',
                    reason=ModelResponseEndReason.REQUEST_INCOMPLETE,
                    usage=model_usage(),
                    incomplete_details=ModelResponseIncompleteDetails(
                        reason="max_output_tokens"
                    ),
                )
            ]
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "incomplete_reason=max_output_tokens",
        ):
            generate_study_card(
                client,
                base_request(),
                {"lesson-01"},
                "request-incomplete",
            )

        self.assertEqual(len(client.requests), 1)

    def test_repair_result_must_pass_full_validation_pipeline(self):
        repaired_output = valid_study_card()
        repaired_output["source_ids"] = ["lesson-02"]
        client = ScriptedModelClient(
            [
                completed_response("not-json"),
                completed_response(json.dumps(repaired_output)),
            ]
        )

        with (
            self.assertLogs(
                "llm_terminal_assistant.structured_output.pipeline",
                level="ERROR",
            ),
            self.assertRaises(StructuredOutputError) as captured_error,
        ):
            generate_study_card(
                client,
                base_request(),
                {"lesson-01"},
                "request-repair-business-error",
            )

        self.assertEqual(
            captured_error.exception.category,
            ErrorCategory.BUSINESS_RULE_VALIDATION_ERROR,
        )
        self.assertEqual(len(client.requests), 2)


if __name__ == "__main__":
    unittest.main()

import json
import unittest

from llm_terminal_assistant.structured_output.errors import (
    ErrorCategory,
    StructuredOutputError,
)
from llm_terminal_assistant.structured_output.pipeline import build_study_card
from llm_terminal_assistant.structured_output.study_card import StudyCard


def valid_study_card() -> dict[str, object]:
    return {
        "title": "Structured output",
        "summary": "Applications validate syntax, structure, and business rules.",
        "questions": [
            "What does JSON Schema validate?",
            "Which checks remain the application's responsibility?",
        ],
        "source_ids": ["lesson-01"],
    }


class StructuredOutputPipelineTests(unittest.TestCase):
    def assert_pipeline_error(
        self,
        model_output: str,
        expected_category: ErrorCategory,
        expected_field_path: str | None,
        *,
        allowed_source_ids: set[str] | None = None,
    ) -> str:
        request_id = "request-for-pipeline-test"
        effective_allowed_source_ids = (
            {"lesson-01"} if allowed_source_ids is None else allowed_source_ids
        )
        with (
            self.assertLogs(
                "llm_terminal_assistant.structured_output.pipeline",
                level="ERROR",
            ) as captured_logs,
            self.assertRaises(StructuredOutputError) as captured_error,
        ):
            build_study_card(
                model_output,
                effective_allowed_source_ids,
                request_id,
            )

        error = captured_error.exception
        self.assertEqual(error.category, expected_category)
        self.assertEqual(error.field_path, expected_field_path)

        log_output = "\n".join(captured_logs.output)
        self.assertIn(f"category={expected_category}", log_output)
        self.assertIn(f"field_path={expected_field_path or 'N/A'}", log_output)
        self.assertIn(f"request_id={request_id}", log_output)
        self.assertNotIn(model_output, log_output)
        return log_output

    def test_returns_project_type_for_valid_object(self):
        card = build_study_card(
            json.dumps(valid_study_card()),
            {"lesson-01", "lesson-02"},
            "request-valid",
        )

        self.assertEqual(
            card,
            StudyCard(
                title="Structured output",
                summary=(
                    "Applications validate syntax, structure, and business rules."
                ),
                questions=[
                    "What does JSON Schema validate?",
                    "Which checks remain the application's responsibility?",
                ],
                source_ids=["lesson-01"],
            ),
        )

    def test_rejects_bad_json_before_returning_project_type(self):
        self.assert_pipeline_error(
            "not-json",
            ErrorCategory.PARSE_ERROR,
            None,
        )

    def test_rejects_truncated_json_before_returning_project_type(self):
        self.assert_pipeline_error(
            '{"title": "truncated", "summary":',
            ErrorCategory.PARSE_ERROR,
            None,
        )

    def test_rejects_missing_required_field_with_its_path(self):
        data = valid_study_card()
        del data["title"]

        self.assert_pipeline_error(
            json.dumps(data),
            ErrorCategory.SCHEMA_VALIDATION_ERROR,
            "title",
        )

    def test_rejects_wrong_field_type_with_its_path(self):
        data = valid_study_card()
        data["questions"] = "not-an-array"

        self.assert_pipeline_error(
            json.dumps(data),
            ErrorCategory.SCHEMA_VALIDATION_ERROR,
            "questions",
        )

    def test_rejects_source_outside_allowed_set(self):
        model_output = json.dumps(valid_study_card())

        self.assert_pipeline_error(
            model_output,
            ErrorCategory.BUSINESS_RULE_VALIDATION_ERROR,
            "source_ids",
            allowed_source_ids={"lesson-02"},
        )


if __name__ == "__main__":
    unittest.main()

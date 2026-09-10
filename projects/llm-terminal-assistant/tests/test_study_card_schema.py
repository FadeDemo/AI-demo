import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "study-card.schema.json"


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


class StudyCardSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def assert_invalid(self, card: dict[str, object]):
        self.assertFalse(self.validator.is_valid(card))

    def test_accepts_valid_study_card(self):
        self.assertTrue(self.validator.is_valid(valid_study_card()))

    def test_rejects_each_missing_required_field(self):
        for field in ("title", "summary", "questions", "source_ids"):
            with self.subTest(field=field):
                card = valid_study_card()
                del card[field]

                self.assert_invalid(card)

    def test_rejects_empty_title(self):
        card = valid_study_card()
        card["title"] = ""

        self.assert_invalid(card)

    def test_rejects_question_count_outside_range(self):
        for questions in (["Only one question"], ["1", "2", "3", "4", "5", "6"]):
            with self.subTest(question_count=len(questions)):
                card = valid_study_card()
                card["questions"] = questions

                self.assert_invalid(card)

    def test_rejects_wrong_field_types(self):
        invalid_values = {
            "title": 1,
            "summary": ["not", "a", "string"],
            "questions": "not an array",
            "source_ids": "not an array",
        }
        for field, value in invalid_values.items():
            with self.subTest(field=field):
                card = valid_study_card()
                card[field] = value

                self.assert_invalid(card)

    def test_rejects_additional_fields(self):
        card = valid_study_card()
        card["difficulty"] = "beginner"

        self.assert_invalid(card)

    def test_rejects_empty_source_id(self):
        card = valid_study_card()
        card["source_ids"] = [""]

        self.assert_invalid(card)

    def test_rejects_duplicate_source_ids(self):
        card = valid_study_card()
        card["source_ids"] = ["lesson-01", "lesson-01"]

        self.assert_invalid(card)

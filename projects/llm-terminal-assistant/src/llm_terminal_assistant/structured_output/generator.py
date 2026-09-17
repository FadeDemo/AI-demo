from dataclasses import replace
from typing import cast

from llm_terminal_assistant.client import ModelClient
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import (
    ModelOutputFormat,
    ModelRequest,
    ModelResponse,
    ModelResponseEndReason,
)
from llm_terminal_assistant.structured_output.errors import (
    ErrorCategory,
    StructuredOutputError,
)
from llm_terminal_assistant.structured_output.pipeline import (
    SCHEMA_FILE_PATH,
    build_study_card,
)
from llm_terminal_assistant.structured_output.schema_validator import (
    load_schema_from_file,
)
from llm_terminal_assistant.structured_output.study_card import StudyCard

MAX_ATTEMPTS = 2

REPAIR_INSTRUCTION = (
    "上一条响应无法按 JSON 语法解析。"
    "请修复该响应，只返回一份完整且符合目标 Schema 的 JSON；"  # noqa: RUF001
    "不要添加代码围栏、解释文字或其他内容。"
)


def _ensure_completed(response: ModelResponse) -> None:
    if response.reason == ModelResponseEndReason.COMPLETED_NORMALLY:
        return

    details = [f"reason={response.reason}"]
    if response.error is not None:
        details.append(
            f"error_code={response.error.code}, message={response.error.message}"
        )
    if response.incomplete_details is not None:
        details.append(f"incomplete_reason={response.incomplete_details.reason}")

    raise RuntimeError(
        "Model response did not complete normally: " + ", ".join(details)
    )


def _build_repair_request(
    request: ModelRequest,
    invalid_output: str,
) -> ModelRequest:
    return replace(
        request,
        messages=[
            *request.messages,
            Message(role="assistant", content=invalid_output),
            Message(role="user", content=REPAIR_INSTRUCTION),
        ],
    )


def generate_study_card(
    client: ModelClient,
    base_request: ModelRequest,
    allowed_source_ids: set[str],
    request_id: str,
) -> StudyCard:
    raw_schema = load_schema_from_file(SCHEMA_FILE_PATH)
    if not isinstance(raw_schema, dict):
        raise ValueError("Invalid study-card schema.")

    schema = cast(dict[str, object], raw_schema)
    current_request = replace(
        base_request,
        output_format=ModelOutputFormat(
            type="json_schema",
            name="study_card",
            schema=schema,
        ),
    )

    for attempt in range(MAX_ATTEMPTS):
        model_response = client.send(current_request)
        _ensure_completed(model_response)

        try:
            return build_study_card(
                model_response.text,
                allowed_source_ids,
                request_id,
            )
        except StructuredOutputError as error:
            if error.category != ErrorCategory.PARSE_ERROR:
                raise

            if attempt == MAX_ATTEMPTS - 1:
                raise

            current_request = _build_repair_request(
                current_request,
                model_response.text,
            )

    raise AssertionError("unreachable")

"""阶段 2：Schema 结构校验。

- 输入：阶段 1 解析得到的数据值；
- 行为：按本次任务定义的 Schema 契约（schemas/ 目录下保存的学习卡片 Schema）
  校验数据值，覆盖必填字段、字段类型、数组元素数量、额外字段限制等；
- 失败：抛出结构校验错误，并尽量携带字段路径，表明哪个字段、哪个元素不满足约束。
"""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from llm_terminal_assistant.structured_output.errors import (
    ErrorCategory,
    StructuredOutputError,
)


def _field_path(error: ValidationError) -> str:
    path_parts = [str(part) for part in error.absolute_path]

    if error.validator == "required" and isinstance(error.instance, dict):
        missing_field = next(
            (field for field in error.validator_value if field not in error.instance),
            None,
        )
        if missing_field is not None:
            path_parts.append(missing_field)

    return ".".join(path_parts) if path_parts else "$"


def validate_schema(schema: dict, data: Any) -> None:
    if not isinstance(schema, dict):
        raise ValueError("Schema must be a dictionary.")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as e:
        raise StructuredOutputError(
            category=ErrorCategory.SCHEMA_VALIDATION_ERROR
        ) from e
    validator = Draft202012Validator(schema)
    try:
        validator.validate(data)
    except ValidationError as e:
        raise StructuredOutputError(
            category=ErrorCategory.SCHEMA_VALIDATION_ERROR,
            field_path=_field_path(e),
        ) from e


def load_schema_from_file(schema_file_path: str | Path) -> Any:
    """从 JSON 文件加载 Schema。

    Args:
        schema_file_path (str): Schema 文件路径。

    Returns:
        Any: 加载后的产物。
    """
    if not schema_file_path:
        raise ValueError("Schema file path must not be empty.")
    with open(schema_file_path, encoding="utf-8") as f:
        schema = json.load(f)
    return schema

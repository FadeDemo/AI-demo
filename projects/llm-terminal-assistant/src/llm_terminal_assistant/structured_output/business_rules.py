"""阶段 3：业务规则校验。

- 输入：通过 Schema 校验的数据值，以及本次模型输入的允许来源 ID 集合；
- 行为：确认数据值中每个来源 ID 都属于该允许集合。这是应用侧的核心检查，
  用来识破模型编造来源，属于 Schema 表达不了的业务正确性；
- 失败：抛出业务规则错误，携带来源 ID 字段的路径信息。
"""

from llm_terminal_assistant.structured_output.errors import (
    ErrorCategory,
    StructuredOutputError,
)


def validate_business_rules(data: dict, allowed_source_ids: set[str]) -> None:
    if data is None:
        raise ValueError("Data must not be None.")
    source_ids = data.get("source_ids")
    if source_ids is None:
        raise ValueError("Data must contain 'source_ids' field.")
    if set(source_ids) - allowed_source_ids:
        field_path = "source_ids"
        raise StructuredOutputError(
            category=ErrorCategory.BUSINESS_RULE_VALIDATION_ERROR, field_path=field_path
        )

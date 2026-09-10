"""验证流水线：编排四个阶段并产出可区分的错误与日志。

- 顺序：解析 → Schema 校验 → 业务规则校验 → 项目类型转换；
- 输入：模型输出文本、允许来源 ID 集合、请求 ID（供日志关联）；
- 合法输出：转换后的项目类型，仅当全部验证通过；
- 失败：按阶段抛出对应类别的错误；错误日志只记录类别、字段路径和请求 ID，
  不记录完整模型输出；
- 备注：语法类格式失败是任务 3 唯一允许修复的类别，本阶段只负责报告。
"""

import logging
from pathlib import Path

from llm_terminal_assistant.structured_output.business_rules import (
    validate_business_rules,
)
from llm_terminal_assistant.structured_output.errors import (
    StructuredOutputError,
)
from llm_terminal_assistant.structured_output.parser import parse_json
from llm_terminal_assistant.structured_output.schema_validator import (
    load_schema_from_file,
    validate_schema,
)
from llm_terminal_assistant.structured_output.study_card import StudyCard

SCHEMA_FILE_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "study-card.schema.json"
)

logger = logging.getLogger(__name__)


def build_study_card(
    model_output: str, allowed_source_ids: set[str], request_id: str
) -> StudyCard:
    try:
        data = parse_json(model_output)
        schema = load_schema_from_file(SCHEMA_FILE_PATH)
        validate_schema(schema, data)
        validate_business_rules(data, allowed_source_ids)
    except StructuredOutputError as e:
        logger.error(
            "category=%s, field_path=%s, request_id=%s",
            e.category,
            e.field_path if e.field_path else "N/A",
            request_id,
        )
        raise
    return StudyCard(**data)

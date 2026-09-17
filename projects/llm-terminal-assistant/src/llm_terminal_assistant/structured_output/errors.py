"""验证流水线的错误类别定义。

本模块只区分模型输出在验证边界上可以触发的三类失败：

- 语法解析失败；
- Schema 结构校验失败；
- 业务规则校验失败；
- 异常或错误对象：携带错误类别与（可能缺失的）字段路径；
  请求 ID 由验证流水线在日志点提供；不得保存或记录完整模型输出。
"""

from enum import StrEnum


class ErrorCategory(StrEnum):
    """错误类别枚举。"""

    PARSE_ERROR = "parse_error"
    SCHEMA_VALIDATION_ERROR = "schema_validation_error"
    BUSINESS_RULE_VALIDATION_ERROR = "business_rule_validation_error"


class StructuredOutputError(Exception):
    """结构化输出错误对象。

    该异常对象携带错误类别与（可能缺失的）字段路径；
    请求 ID 由验证流水线在日志点提供；不得保存或记录完整模型输出。
    """

    def __init__(self, category: ErrorCategory, field_path: str | None = None):
        message: str = f"{category}"
        if field_path:
            message += f" at {field_path}"
        super().__init__(message)
        self.category = category
        self.field_path = field_path

"""阶段 1：语法解析。

- 输入：模型返回的文本（str）；
- 行为：这段文本本身必须是一份完整、合法的 JSON 文档，
  按 JSON 语法将其解码为可操作的数据值；
- 失败：文本是自然语言正文、带有代码围栏或不完整时，明确抛出语法解析失败；
  不尝试从正文中提取、修补或猜测；
- 实现形态：无状态纯函数即可（接收文本、返回数据值或抛出语法错误），
  无需类；错误类别从 errors.py 取。
"""

import json
from typing import Any

from llm_terminal_assistant.structured_output.errors import (
    ErrorCategory,
    StructuredOutputError,
)


def parse_json(json_text: str) -> Any:
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        raise StructuredOutputError(ErrorCategory.PARSE_ERROR) from e

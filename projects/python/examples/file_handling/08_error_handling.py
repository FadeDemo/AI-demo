"""Demonstrate file-loading error handling with module-level logging."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_json_document(path: Path) -> object | None:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        logger.error("文件不存在: %s", path)
    except UnicodeDecodeError:
        logger.error("文件不是有效的 UTF-8 文本: %s", path)
    except json.JSONDecodeError as error:
        logger.error("JSON 格式错误: path=%s line=%s", path, error.lineno)

    return None


load_json_document(Path("data/config1.json"))

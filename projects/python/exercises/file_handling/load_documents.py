import json
import logging
from pathlib import Path

from document_loader import Document, read_json, read_text

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".txt", ".md", ".json"}


def load_documents(root: Path) -> list[Document]:
    documents = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            try:
                if path.suffix.lower() == ".txt" or path.suffix.lower() == ".md":
                    content = read_text(path)
                else:
                    content = json.dumps(read_json(path))
            except FileNotFoundError:
                logger.error("文件不存在: %s", path)
            except UnicodeDecodeError:
                logger.error("文件不是有效的 UTF-8 文本: %s", path)
            except json.JSONDecodeError as error:
                logger.error("JSON 格式错误: path=%s line=%s", path, error.lineno)
            if content is not None and content.strip() != "":
                documents.append(
                    Document(
                        content=content,
                        source=path.relative_to(root).as_posix(),
                        metadata={
                            "file_name": path.name,
                            "file_type": path.suffix.lower(),
                            "size_bytes": path.stat().st_size,
                        },
                    )
                )
    sorted_documents = sorted(documents, key=lambda doc: doc.source)
    return sorted_documents

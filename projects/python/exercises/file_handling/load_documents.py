import json
import logging
from pathlib import Path

from document_loader import Document, read_json, read_text

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".txt", ".md", ".json"}


def load_documents(root: Path) -> list[Document]:
    documents: list[Document] = []
    for path in root.rglob("*"):
        try:
            suffix = path.suffix.lower()
            if not path.is_file() or suffix not in SUPPORTED_SUFFIXES:
                continue

            if suffix in {".txt", ".md"}:
                content = read_text(path)
            else:
                content = json.dumps(read_json(path), ensure_ascii=False)

            if not content.strip():
                continue

            documents.append(
                Document(
                    content=content,
                    source=path.relative_to(root).as_posix(),
                    metadata={
                        "file_name": path.name,
                        "file_type": suffix,
                        "size_bytes": path.stat().st_size,
                    },
                )
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            logger.error(
                "加载文件失败: path=%s error_type=%s",
                path,
                type(error).__name__,
                exc_info=True,
            )

    return sorted(documents, key=lambda document: document.source)

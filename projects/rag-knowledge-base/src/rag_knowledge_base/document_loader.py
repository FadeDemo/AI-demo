import logging
from pathlib import Path

from rag_knowledge_base.document import Document

logger = logging.getLogger(__name__)


def load_document(path: Path, corpus_root: Path) -> Document | None:
    if path.is_dir():
        raise ValueError(f"Expected a file, got a directory: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if text == "":
        return None
    relative_path = path.relative_to(corpus_root).as_posix()
    return Document(
        doc_id=relative_path,
        title=path.stem,
        text=text,
        source=relative_path,
    )


def load_documents(corpus_root: Path) -> list[Document]:
    if not corpus_root.exists():
        raise FileNotFoundError(f"Corpus root directory does not exist: {corpus_root}")
    if not corpus_root.is_dir():
        raise NotADirectoryError(f"Expected a directory, got a file: {corpus_root}")
    documents: list[Document] = []
    for path in corpus_root.rglob("*"):
        if not path.is_file() or (
            path.is_file() and path.suffix.lower() not in {".txt", ".md"}
        ):
            continue
        document = load_document(path, corpus_root)
        if document is not None:
            documents.append(document)
        else:
            logger.warning("跳过空文件，正文为空：%s", path)
    return documents

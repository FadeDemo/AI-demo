import json
from dataclasses import dataclass
from typing import Any

from rag_knowledge_base.document import Document


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    document_version: str
    title: str
    source: str
    start: int
    end: int
    text: str
    section: str | None = None


def split_text(text: str, chunk_size: int, overlap: int) -> list[tuple[int, int, str]]:
    def check_int(value: Any) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"Expected an integer, got {type(value)}")
        if value < 0:
            raise ValueError(f"Expected a non-negative integer, got {value}")

    check_int(chunk_size)
    if chunk_size == 0:
        raise ValueError("Chunk size must be positive")
    check_int(overlap)
    if overlap >= chunk_size:
        raise ValueError(
            f"Overlap must be less than chunk size, got {overlap} >= {chunk_size}"
        )
    if not text:
        return []
    result = []
    for i in range(0, len(text), chunk_size - overlap):
        start = i
        end = min(i + chunk_size, len(text))
        chunk = text[start:end]
        result.append((start, end, chunk))
        if end == len(text):
            break
    return result


def chunk_document(
    document: Document,
    document_version: str,
    chunk_size: int,
    overlap: int,
) -> list[Chunk]:
    chunks = []
    splited_text = split_text(document.text, chunk_size, overlap)
    for start, end, text in splited_text:
        chunk_id = {
            "doc_id": document.doc_id,
            "document_version": document_version,
            "chunk_size": chunk_size,
            "overlap": overlap,
            "start": start,
            "end": end,
        }
        chunk = Chunk(
            chunk_id=json.dumps(chunk_id),
            doc_id=document.doc_id,
            document_version=document_version,
            title=document.title,
            source=document.source,
            start=start,
            end=end,
            text=text,
        )
        chunks.append(chunk)
    return chunks


def prepare_chunks(
    documents: list[Document],
    document_version: str,
    chunk_size: int,
    overlap: int,
) -> list[Chunk]:
    chunks = []
    for document in documents:
        chunks.extend(chunk_document(document, document_version, chunk_size, overlap))
    return chunks

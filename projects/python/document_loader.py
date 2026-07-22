"""Small, standard-library-only helpers for loading local documents."""

import csv
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SUPPORTED_SUFFIXES = {".txt", ".md", ".json"}


@dataclass
class Document:
    """A normalized document ready for later chunking and retrieval."""

    content: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


def read_text(path: Path) -> str:
    """Read a small UTF-8 text file in one operation."""

    return path.read_text(encoding="utf-8")


def iter_non_empty_lines(path: Path) -> Iterator[str]:
    """Yield stripped, non-empty lines without loading the whole file."""

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            normalized = line.strip()
            if normalized:
                yield normalized


def read_json(path: Path) -> Any:
    """Read one JSON value from a UTF-8 file."""

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read non-empty JSON Lines records and report the failing line."""

    records = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from error
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            records.append(record)
    return records


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a UTF-8 CSV file as dictionaries keyed by its header row."""

    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def find_supported_files(root: Path) -> list[Path]:
    """Return supported files recursively in a deterministic order."""

    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )


def read_text_document(path: Path, root: Path) -> Document:
    """Convert one text-like file to the shared Document structure."""

    return Document(
        content=read_text(path),
        source=path.relative_to(root).as_posix(),
        metadata={
            "file_name": path.name,
            "file_type": path.suffix.lower(),
        },
    )

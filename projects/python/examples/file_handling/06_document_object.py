from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Document:
    content: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


def read_text_document(path: Path, root: Path) -> Document:
    content = path.read_text(encoding="utf-8")
    return Document(
        content=content,
        source=path.relative_to(root).as_posix(),
        metadata={
            "file_name": path.name,
            "file_type": path.suffix.lower(),
        },
    )


root = Path("data/knowledge")
document = read_text_document(root / "guide.md", root)
print(document.source)  # guide.md
print(document.metadata["file_type"])  # .md

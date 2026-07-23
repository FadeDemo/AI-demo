from pathlib import Path

SUPPORTED_SUFFIXES = {".txt", ".md", ".json"}
knowledge_dir = Path("data/knowledge")

paths = sorted(
    path
    for path in knowledge_dir.rglob("*")
    if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
)
# [PosixPath('data/knowledge/faq.txt'), PosixPath('data/knowledge/guide.md'),
#  PosixPath('data/knowledge/metadata.json')]
print(paths)

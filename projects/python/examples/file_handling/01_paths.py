from pathlib import Path

knowledge_dir = Path("data/knowledge")
document_path = knowledge_dir / "guide.md"

print(document_path.name)  # guide.md
print(document_path.suffix)  # .md
print(document_path.exists())  # True

print(Path.cwd())
print(Path("data/knowledge").resolve())

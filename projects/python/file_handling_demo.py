"""Run the main file-reading workflows against the sample data."""

from pathlib import Path

from document_loader import (
    find_supported_files,
    iter_non_empty_lines,
    read_csv,
    read_json,
    read_jsonl,
    read_text_document,
)

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"


def main() -> None:
    guide_path = DATA_DIR / "knowledge" / "guide.md"

    print("Markdown title:", guide_path.read_text(encoding="utf-8").splitlines()[0])
    print("Config:", read_json(DATA_DIR / "config.json"))
    print("JSONL records:", len(read_jsonl(DATA_DIR / "documents.jsonl")))
    print("CSV rows:", len(read_csv(DATA_DIR / "articles.csv")))
    print("Corpus lines:", list(iter_non_empty_lines(DATA_DIR / "large-corpus.txt")))

    paths = find_supported_files(DATA_DIR / "knowledge")
    documents = [read_text_document(path, DATA_DIR / "knowledge") for path in paths]
    print("Documents:", [document.source for document in documents])


if __name__ == "__main__":
    main()

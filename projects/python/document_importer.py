import argparse
import sys
from pathlib import Path

from document_loader import Document
from exercises.file_handling.load_documents import load_documents


def import_documents(path: str) -> list[Document]:
    """Import documents from a given file path."""
    return load_documents(Path(path))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import documents from the given directory."
    )
    parser.add_argument(
        "path", type=str, help="Path to the directory containing documents."
    )
    args = parser.parse_args()
    if not Path(args.path).exists() or not Path(args.path).is_dir():
        print(f"Error: The path '{args.path}' does not exist or is not a directory.")
        sys.exit(1)
    documents = import_documents(args.path)
    print(f"Imported {len(documents)} documents from {args.path}")
    for doc in documents:
        print(f"Imported Document: {doc}")

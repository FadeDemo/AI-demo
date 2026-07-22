import tempfile
import unittest
from pathlib import Path

from document_loader import (
    find_supported_files,
    iter_non_empty_lines,
    read_csv,
    read_json,
    read_jsonl,
    read_text_document,
)

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data"


class DocumentLoaderTest(unittest.TestCase):
    def test_read_sample_formats(self) -> None:
        self.assertEqual(read_json(DATA_DIR / "config.json")["language"], "zh-CN")
        self.assertEqual(len(read_jsonl(DATA_DIR / "documents.jsonl")), 3)
        self.assertEqual(len(read_csv(DATA_DIR / "articles.csv")), 3)
        self.assertEqual(
            list(iter_non_empty_lines(DATA_DIR / "large-corpus.txt")),
            ["第一条有效记录", "第二条有效记录", "第三条有效记录"],
        )

    def test_find_and_normalize_documents(self) -> None:
        knowledge_dir = DATA_DIR / "knowledge"
        paths = find_supported_files(knowledge_dir)

        self.assertEqual(
            [path.name for path in paths],
            ["faq.txt", "guide.md", "metadata.json"],
        )

        document = read_text_document(knowledge_dir / "guide.md", knowledge_dir)
        self.assertEqual(document.source, "guide.md")
        self.assertEqual(document.metadata["file_type"], ".md")
        self.assertIn("文件处理示例", document.content)

    def test_invalid_jsonl_reports_line_number(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.jsonl"
            path.write_text('{"ok": true}\nnot-json\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, r"broken\.jsonl:2"):
                read_jsonl(path)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from exercises.file_handling.load_documents import load_documents


class LoadDocumentsAcceptanceTest(unittest.TestCase):
    def test_empty_directory_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_documents(Path(directory)), [])

    def test_loads_supported_files_recursively_and_records_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "nested"
            nested.mkdir()

            text_path = root / "intro.txt"
            markdown_path = nested / "guide.md"
            json_path = nested / "metadata.json"
            text_path.write_text("文本内容\n", encoding="utf-8")
            markdown_path.write_text("# 指南\n", encoding="utf-8")
            json_path.write_text('{"topic": "文件处理"}\n', encoding="utf-8")
            (root / "empty.txt").write_text(" \n", encoding="utf-8")
            (root / "ignored.csv").write_text("title\n示例\n", encoding="utf-8")

            documents = load_documents(root)
            documents_by_source = {document.source: document for document in documents}

            self.assertEqual(
                set(documents_by_source),
                {"intro.txt", "nested/guide.md", "nested/metadata.json"},
            )

            for source, document in documents_by_source.items():
                path = root / source
                self.assertIsInstance(document.content, str)
                self.assertFalse(Path(document.source).is_absolute())
                self.assertEqual(document.metadata["file_name"], path.name)
                self.assertEqual(document.metadata["file_type"], path.suffix)
                self.assertEqual(document.metadata["size_bytes"], path.stat().st_size)

            self.assertIn(
                "文件处理", documents_by_source["nested/metadata.json"].content
            )

    def test_result_order_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "z.txt").write_text("z", encoding="utf-8")
            (root / "a.txt").write_text("a", encoding="utf-8")
            (root / "m.md").write_text("m", encoding="utf-8")

            first_sources = [document.source for document in load_documents(root)]
            second_sources = [document.source for document in load_documents(root)]

            self.assertEqual(first_sources, second_sources)
            self.assertEqual(first_sources, sorted(first_sources))

    def test_non_utf8_file_is_logged_and_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "valid.txt").write_text("有效内容", encoding="utf-8")
            (root / "broken.txt").write_bytes(b"\xff\xfe")

            with self.assertLogs(level="ERROR") as captured:
                documents = load_documents(root)

            self.assertEqual(
                [document.source for document in documents],
                ["valid.txt"],
            )
            log_output = "\n".join(captured.output)
            self.assertIn("broken.txt", log_output)
            self.assertIn("UnicodeDecodeError", log_output)

    def test_invalid_json_is_logged_and_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "valid.md").write_text("# 有效文档", encoding="utf-8")
            (root / "broken.json").write_text("{not-json}", encoding="utf-8")

            with self.assertLogs(level="ERROR") as captured:
                documents = load_documents(root)

            self.assertEqual(
                [document.source for document in documents],
                ["valid.md"],
            )
            log_output = "\n".join(captured.output)
            self.assertIn("broken.json", log_output)
            self.assertIn("JSONDecodeError", log_output)

    def test_permission_error_is_logged_and_other_files_are_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid_path = root / "valid.txt"
            blocked_path = root / "blocked.txt"
            valid_path.write_text("有效内容", encoding="utf-8")
            blocked_path.write_text("无法读取", encoding="utf-8")
            original_read_text = Path.read_text

            def read_text_with_denial(
                path: Path, *args: object, **kwargs: object
            ) -> str:
                if path == blocked_path:
                    raise PermissionError("access denied")
                return original_read_text(path, *args, **kwargs)

            with (
                patch.object(Path, "read_text", new=read_text_with_denial),
                self.assertLogs(level="ERROR") as captured,
            ):
                documents = load_documents(root)

            self.assertEqual([document.source for document in documents], ["valid.txt"])
            log_output = "\n".join(captured.output)
            self.assertIn("blocked.txt", log_output)
            self.assertIn("PermissionError", log_output)


if __name__ == "__main__":
    unittest.main()

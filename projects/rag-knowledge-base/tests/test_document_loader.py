"""验证单文件和目录读取的文档字段与失败行为。"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from rag_knowledge_base.document import Document
from rag_knowledge_base.document_loader import load_document, load_documents


class DocumentLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        temporary_root = repository_root / ".agent-tmp"
        if temporary_root.is_symlink() or not temporary_root.resolve().is_relative_to(
            repository_root
        ):
            raise RuntimeError("Test temporary files must stay in the repository")
        temporary_root.mkdir(exist_ok=True)
        directory = TemporaryDirectory(
            prefix="document-loader-test-", dir=temporary_root
        )
        self.addCleanup(directory.cleanup)
        self.corpus_root = Path(directory.name)

    def test_loads_fields_and_normalizes_text(self) -> None:
        folder = self.corpus_root / "network"
        folder.mkdir()
        content = " \r\n# 超时\r\n\r\n请求超时后有限重试。\r\n\t "

        for suffix in (".md", ".txt"):
            with self.subTest(suffix=suffix):
                path = folder / f"超时说明.v1{suffix}"
                path.write_bytes(content.encode("utf-8"))

                document = load_document(path, self.corpus_root)

                self.assertEqual(
                    document,
                    Document(
                        doc_id=f"network/超时说明.v1{suffix}",
                        title="超时说明.v1",
                        text="# 超时\n\n请求超时后有限重试。",
                        source=f"network/超时说明.v1{suffix}",
                    ),
                )

    def test_returns_none_for_empty_or_whitespace_only_text(self) -> None:
        path = self.corpus_root / "empty.txt"
        for content in ("", " \r\n\t "):
            with self.subTest(content=content):
                path.write_bytes(content.encode("utf-8"))

                self.assertIsNone(load_document(path, self.corpus_root))

    def test_missing_file_raises(self) -> None:
        path = self.corpus_root / "missing.md"

        with self.assertRaises(FileNotFoundError):
            load_document(path, self.corpus_root)

    def test_invalid_utf8_raises(self) -> None:
        path = self.corpus_root / "invalid.txt"
        path.write_bytes(b"\xff")

        with self.assertRaises(UnicodeDecodeError):
            load_document(path, self.corpus_root)

    def test_read_failure_propagates(self) -> None:
        path = self.corpus_root / "unreadable.md"
        path.write_text("# 超时\n", encoding="utf-8")
        error = PermissionError("simulated read failure")

        with (
            patch.object(Path, "read_text", side_effect=error),
            self.assertRaises(PermissionError) as caught,
        ):
            load_document(path, self.corpus_root)

        self.assertIs(caught.exception, error)

    def test_directory_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            load_document(self.corpus_root, self.corpus_root)

    def test_loads_directory_recursively_with_root_relative_ids(self) -> None:
        fixtures = {
            "预算.md": "发送前检查上下文长度。",
            "network/超时.md": "请求超时后有限重试。",
            "network/retry/超时.txt": "重试次数应有上限。",
        }
        expected = {}
        for relative_path, text in fixtures.items():
            path = self.corpus_root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            expected[relative_path] = Document(
                doc_id=relative_path,
                title=path.stem,
                text=text,
                source=relative_path,
            )

        with self.assertNoLogs("rag_knowledge_base.document_loader", level="WARNING"):
            documents = load_documents(self.corpus_root)

        self.assertEqual(len(documents), len(fixtures))
        self.assertEqual({doc.doc_id: doc for doc in documents}, expected)

    def test_directory_filters_file_types_and_non_files(self) -> None:
        (self.corpus_root / "folder.md").mkdir()
        for name in ("超时.MD", "日志.TxT"):
            (self.corpus_root / name).write_text("用于检索的正文。", encoding="utf-8")
        (self.corpus_root / "ignored.json").write_bytes(b"\xff")

        documents = load_documents(self.corpus_root)

        self.assertEqual(len(documents), 2)
        self.assertEqual({doc.doc_id for doc in documents}, {"超时.MD", "日志.TxT"})

    def test_directory_skips_empty_files_and_logs_their_paths_and_reason(self) -> None:
        empty = self.corpus_root / "empty.md"
        empty.write_bytes(b"")
        folder = self.corpus_root / "nested"
        folder.mkdir()
        whitespace = folder / "whitespace.txt"
        whitespace.write_bytes(b" \r\n\t ")
        (self.corpus_root / "valid.md").write_text("有效正文。", encoding="utf-8")

        with self.assertLogs(
            "rag_knowledge_base.document_loader", level="WARNING"
        ) as captured:
            documents = load_documents(self.corpus_root)

        self.assertEqual([doc.doc_id for doc in documents], ["valid.md"])
        self.assertEqual(len(captured.records), 2)
        messages = [record.getMessage() for record in captured.records]
        for path in (empty, whitespace):
            self.assertTrue(
                any(
                    str(path) in message and "正文为空" in message
                    for message in messages
                ),
                f"Missing empty-file reason and path for {path}",
            )

    def test_directory_keeps_existing_records_when_another_file_is_added(self) -> None:
        folder = self.corpus_root / "network"
        folder.mkdir()
        (folder / "超时.md").write_text("请求超时后有限重试。", encoding="utf-8")
        original = {doc.doc_id: doc for doc in load_documents(self.corpus_root)}

        repeated = {doc.doc_id: doc for doc in load_documents(self.corpus_root)}
        self.assertEqual(repeated, original)

        (self.corpus_root / "a.md").write_text("另一篇文档。", encoding="utf-8")
        expanded = {doc.doc_id: doc for doc in load_documents(self.corpus_root)}

        self.assertEqual(len(expanded), len(original) + 1)
        for doc_id, document in original.items():
            self.assertEqual(expanded[doc_id], document)

    def test_missing_directory_root_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_documents(self.corpus_root / "missing")

    def test_file_directory_root_raises(self) -> None:
        path = self.corpus_root / "file.md"
        path.write_text("正文。", encoding="utf-8")

        with self.assertRaises(NotADirectoryError):
            load_documents(path)

    def test_directory_invalid_utf8_raises(self) -> None:
        folder = self.corpus_root / "nested"
        folder.mkdir()
        (folder / "invalid.txt").write_bytes(b"\xff")

        with self.assertRaises(UnicodeDecodeError):
            load_documents(self.corpus_root)

    def test_directory_read_failure_propagates(self) -> None:
        path = self.corpus_root / "unreadable.md"
        path.write_text("正文。", encoding="utf-8")
        error = PermissionError("simulated read failure")

        with (
            patch.object(Path, "read_text", side_effect=error),
            self.assertRaises(PermissionError) as caught,
        ):
            load_documents(self.corpus_root)

        self.assertIs(caught.exception, error)


if __name__ == "__main__":
    unittest.main()

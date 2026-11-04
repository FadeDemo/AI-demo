"""通过命令行入口验证文档加载、输出和退出状态。"""

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        temporary_root = repository_root / ".agent-tmp"
        if temporary_root.is_symlink() or not temporary_root.resolve().is_relative_to(
            repository_root
        ):
            raise RuntimeError("Test temporary files must stay in the repository")
        temporary_root.mkdir(exist_ok=True)
        directory = TemporaryDirectory(prefix="rag-cli-test-", dir=temporary_root)
        self.addCleanup(directory.cleanup)
        self.working_directory = Path(directory.name)
        self.corpus_root = self.working_directory / "docs"
        self.corpus_root.mkdir()

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", "-m", "rag_knowledge_base", *arguments],
            cwd=self.working_directory,
            capture_output=True,
            encoding="utf-8",
            check=False,
            timeout=5,
        )

    def test_loads_relative_directory_and_prints_count_and_ids(self) -> None:
        (self.corpus_root / "预算.md").write_text("发送前检查长度。", encoding="utf-8")
        nested = self.corpus_root / "network"
        nested.mkdir()
        (nested / "超时.txt").write_text("请求超时后有限重试。", encoding="utf-8")

        result = self.run_cli("docs")

        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], "载入 2 个文档")
        self.assertCountEqual(lines[1:], ["预算.md", "network/超时.txt"])
        self.assertEqual(result.stderr, "")

    def test_empty_directory_prints_zero_documents(self) -> None:
        result = self.run_cli("docs")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["载入 0 个文档"])
        self.assertEqual(result.stderr, "")

    def test_help_describes_corpus_root(self) -> None:
        result = self.run_cli("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("corpus_root", result.stdout)
        self.assertIn("语料根目录", result.stdout)
        self.assertIn("--doc-id", result.stdout)
        self.assertIn("查看指定编号的文档", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_lookup_prints_matching_document_fields(self) -> None:
        fixtures = {
            "超时.md": "# 超时\n\n请求超时后有限重试。",
            "network/超时.md": "# 超时\n\n连接超时需要检查网络。",
        }
        for relative_path, text in fixtures.items():
            path = self.corpus_root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        for relative_path, text in fixtures.items():
            with self.subTest(doc_id=relative_path):
                result = self.run_cli("docs", "--doc-id", relative_path)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"编号为 {relative_path}", result.stdout)
                self.assertIn("标题是 超时", result.stdout)
                self.assertIn(f"来源是 {relative_path}", result.stdout)
                self.assertIn(text, result.stdout)
                self.assertEqual(result.stderr, "")
                for other_id, other_text in fixtures.items():
                    if other_id != relative_path:
                        self.assertNotIn(other_text, result.stdout)

    def test_unknown_id_exits_with_error(self) -> None:
        (self.corpus_root / "超时.md").write_text("请求超时。", encoding="utf-8")

        for doc_id in ("不存在.md", "超时"):
            with self.subTest(doc_id=doc_id):
                result = self.run_cli("docs", "--doc-id", doc_id)

                self.assertEqual(result.returncode, 2)
                self.assertIn(f"未找到编号为 {doc_id} 的文档", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_missing_root_argument_exits_with_usage_error(self) -> None:
        result = self.run_cli()

        self.assertEqual(result.returncode, 2)
        self.assertIn("corpus_root", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_loading_failure_exits_unsuccessfully(self) -> None:
        (self.working_directory / "file.md").write_text("正文。", encoding="utf-8")
        (self.corpus_root / "invalid.txt").write_bytes(b"\xff")
        cases = (
            ("missing", "FileNotFoundError"),
            ("file.md", "NotADirectoryError"),
            ("docs", "UnicodeDecodeError"),
        )

        for argument, error_name in cases:
            with self.subTest(argument=argument):
                result = self.run_cli(argument)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn(error_name, result.stderr)
                self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()

"""通过命令行入口验证文档加载、关键词检索、输出和退出状态。"""

import re
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

    def write_course_corpus(self) -> dict[str, str]:
        fixtures = {
            "预算.md": "# 预算\n\n发送前检查上下文长度。",
            "日志.md": "# 日志\n\n记录请求耗时与超时类别。",
            "超时.md": "# 超时\n\n请求超时后有限重试。",
        }
        for name, text in fixtures.items():
            (self.corpus_root / name).write_text(text, encoding="utf-8")
        return fixtures

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
        self.assertIn("--query", result.stdout)
        self.assertIn("查询相关文档", result.stdout)
        self.assertIn("--method", result.stdout)
        self.assertIn("keyword", result.stdout)
        self.assertIn("--k", result.stdout)
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

    def test_search_prints_course_ranking_scores_and_document_fields(self) -> None:
        fixtures = self.write_course_corpus()

        result = self.run_cli(
            "docs", "--query", "请求超时", "--method", "keyword", "--k", "5"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            re.findall(r"^编号为 (\S+) 的文档", result.stdout, re.MULTILINE),
            ["超时.md", "日志.md"],
        )
        for doc_id, score in (("超时.md", 3), ("日志.md", 2)):
            with self.subTest(doc_id=doc_id):
                self.assertIn(f"标题是 {Path(doc_id).stem}，", result.stdout)
                self.assertIn(fixtures[doc_id], result.stdout)
                self.assertIn(f"来源是 {doc_id}，匹配得分：{score}", result.stdout)
        self.assertNotIn("预算.md", result.stdout)

    def test_search_defaults_to_keyword_and_five_results_with_stable_ties(self) -> None:
        for name in ("f", "e", "d", "c", "b", "a"):
            (self.corpus_root / f"{name}.md").write_text("发生超时。", encoding="utf-8")

        result = self.run_cli("docs", "--query", "超时")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            re.findall(r"^编号为 (\S+) 的文档", result.stdout, re.MULTILINE),
            ["a.md", "b.md", "c.md", "d.md", "e.md"],
        )
        self.assertEqual(result.stdout.count("匹配得分：1"), 5)

    def test_search_k_one_returns_only_the_highest_scoring_document(self) -> None:
        self.write_course_corpus()

        result = self.run_cli("docs", "--query", "请求超时", "--k", "1")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            re.findall(r"^编号为 (\S+) 的文档", result.stdout, re.MULTILINE),
            ["超时.md"],
        )
        self.assertIn("来源是 超时.md，匹配得分：3", result.stdout)

    def test_search_empty_or_unmatched_queries_report_no_matches(self) -> None:
        self.write_course_corpus()

        for query in ("", " \t\n", "，！？", "火山"):
            with self.subTest(query=query):
                result = self.run_cli("docs", "--query", query)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "未找到匹配的文档")
                self.assertEqual(result.stderr, "")

    def test_search_empty_corpus_reports_no_matches(self) -> None:
        result = self.run_cli("docs", "--query", "请求超时")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "未找到匹配的文档")
        self.assertEqual(result.stderr, "")

    def test_search_invalid_k_exits_with_the_expected_error(self) -> None:
        self.write_course_corpus()
        cases = (
            ("0", "k must be a positive integer"),
            ("-1", "k must be a positive integer"),
            ("1.5", "invalid int value"),
            ("abc", "invalid int value"),
        )

        for query in ("请求超时", ""):
            for k, message in cases:
                with self.subTest(query=query, k=k):
                    result = self.run_cli("docs", "--query", query, "--k", k)

                    self.assertEqual(result.returncode, 2)
                    self.assertIn(message, result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertEqual(result.stdout, "")

    def test_search_and_document_lookup_are_mutually_exclusive(self) -> None:
        cases = (
            ("--query", "请求超时", "--doc-id", "超时.md"),
            ("--doc-id", "超时.md", "--query", ""),
        )

        for arguments in cases:
            with self.subTest(arguments=arguments):
                result = self.run_cli("docs", *arguments)

                self.assertEqual(result.returncode, 2)
                self.assertIn("not allowed with argument", result.stderr)
                self.assertIn("--query", result.stderr)
                self.assertIn("--doc-id", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_search_rejects_unsupported_methods(self) -> None:
        result = self.run_cli("docs", "--query", "请求超时", "--method", "vector")

        self.assertEqual(result.returncode, 2)
        self.assertIn("--method", result.stderr)
        self.assertIn("invalid choice", result.stderr)
        self.assertIn("vector", result.stderr)
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

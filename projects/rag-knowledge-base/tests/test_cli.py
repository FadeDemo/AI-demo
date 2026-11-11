"""通过命令行入口验证文档加载、两种检索方法、输出和退出状态。"""

import re
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, call, patch

import numpy as np

from rag_knowledge_base import vector_retrieval
from rag_knowledge_base.cli import main


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

    def run_main(self, *arguments: str) -> tuple[int, str, str]:
        stdout = StringIO()
        stderr = StringIO()
        returncode = 0
        with (
            patch.object(
                sys,
                "argv",
                ["rag-knowledge-base", str(self.corpus_root), *arguments],
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            try:
                main()
            except SystemExit as error:
                returncode = error.code
        return returncode, stdout.getvalue(), stderr.getvalue()

    def make_vector_model(
        self, fixtures: dict[str, str]
    ) -> tuple[Mock, dict[str, np.ndarray]]:
        vectors = {
            "预算.md": [-1.0, 0.0],
            "日志.md": [1.0, 0.0],
            "超时.md": [1.0, 0.0],
        }
        embeddings_by_input = {
            f"passage: {Path(doc_id).stem}\n{text}": np.asarray(
                vectors[doc_id], dtype=np.float32
            )
            for doc_id, text in fixtures.items()
        }
        embeddings_by_input["query: 请求超时"] = np.asarray(
            [1.0, 0.0], dtype=np.float32
        )
        model = Mock(
            spec=["encode", "tokenizer", "max_seq_length", "get_embedding_dimension"]
        )
        model.max_seq_length = 512
        model.get_embedding_dimension.return_value = 2
        model.tokenizer.return_value = {"input_ids": [101, 102, 103]}
        model.encode.side_effect = lambda text, normalize_embeddings: (
            embeddings_by_input[text]
        )
        return model, embeddings_by_input

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
        self.assertIn("vector", result.stdout)
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
        self.assertNotRegex(result.stdout, r"(?m)^查询 ")
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

    def test_repeated_keyword_queries_print_independent_result_groups(self) -> None:
        fixtures = self.write_course_corpus()
        queries = ("请求超时", "", "预算", "火山", "日志", "请求超时")
        arguments = ["docs", "--method", "keyword", "--k", "1"]
        for query in queries:
            arguments.extend(("--query", query))

        result = self.run_cli(*arguments)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        groups = re.findall(
            r"^查询 ([^\n]*)\n(.*?)(?=^查询 |\Z)",
            result.stdout,
            re.MULTILINE | re.DOTALL,
        )
        self.assertEqual([query for query, _ in groups], list(queries))
        expected = [
            [("超时.md", 3)],
            [],
            [("预算.md", 1)],
            [],
            [("日志.md", 1)],
            [("超时.md", 3)],
        ]
        for (query, output), expected_results in zip(groups, expected):
            with self.subTest(query=query):
                self.assertEqual(
                    re.findall(r"^编号为 (\S+) 的文档", output, re.MULTILINE),
                    [doc_id for doc_id, _ in expected_results],
                )
                self.assertEqual(
                    re.findall(r"匹配得分：([^\s]+)", output),
                    [str(score) for _, score in expected_results],
                )
                for doc_id, _ in expected_results:
                    self.assertIn(fixtures[doc_id], output)
                    self.assertIn(f"标题是 {Path(doc_id).stem}，", output)
                    self.assertIn(f"来源是 {doc_id}，", output)
                if not expected_results:
                    self.assertEqual(output, "未找到匹配的文档\n")

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
        result = self.run_cli("docs", "--query", "请求超时", "--method", "unknown")

        self.assertEqual(result.returncode, 2)
        self.assertIn("--method", result.stderr)
        self.assertIn("invalid choice", result.stderr)
        self.assertIn("unknown", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_vector_search_encodes_inputs_and_prints_ranked_document_fields(
        self,
    ) -> None:
        fixtures = self.write_course_corpus()
        expected = [("日志.md", 1.0), ("超时.md", 1.0), ("预算.md", -1.0)]
        expected_cache = Path(__file__).resolve().parents[3] / ".cache" / "huggingface"

        for k in (1, 2, 5):
            with self.subTest(k=k):
                model, embeddings_by_input = self.make_vector_model(fixtures)
                with patch(
                    "sentence_transformers.SentenceTransformer", return_value=model
                ) as constructor:
                    returncode, stdout, stderr = self.run_main(
                        "--query", "请求超时", "--method", "vector", "--k", str(k)
                    )

                self.assertEqual(returncode, 0, stderr)
                self.assertEqual(stderr, "")
                self.assertNotRegex(stdout, r"(?m)^查询 ")
                self.assertEqual(
                    re.findall(r"^编号为 (\S+) 的文档", stdout, re.MULTILINE),
                    [doc_id for doc_id, _ in expected[:k]],
                )
                self.assertEqual(
                    [
                        float(score)
                        for score in re.findall(r"匹配得分：([^\s]+)", stdout)
                    ],
                    [score for _, score in expected[:k]],
                )
                for doc_id, _ in expected[:k]:
                    self.assertIn(f"标题是 {Path(doc_id).stem}，", stdout)
                    self.assertIn(fixtures[doc_id], stdout)
                    self.assertIn(f"来源是 {doc_id}，", stdout)

                constructor.assert_called_once()
                self.assertEqual(
                    constructor.call_args.args, ("intfloat/multilingual-e5-small",)
                )
                self.assertEqual(
                    constructor.call_args.kwargs["revision"],
                    "fd1525a9fd15316a2d503bf26ab031a61d056e98",
                )
                self.assertEqual(
                    Path(constructor.call_args.kwargs["cache_folder"]).resolve(),
                    expected_cache,
                )
                self.assertEqual(model.encode.call_count, len(fixtures) + 1)
                model.encode.assert_has_calls(
                    [
                        call(text, normalize_embeddings=True)
                        for text in embeddings_by_input
                    ],
                    any_order=True,
                )
                self.assertEqual(
                    model.encode.call_args_list[-1],
                    call("query: 请求超时", normalize_embeddings=True),
                )
                self.assertEqual(model.tokenizer.call_count, len(fixtures))
                model.tokenizer.assert_has_calls(
                    [
                        call(text, truncation=False)
                        for text in embeddings_by_input
                        if text.startswith("passage: ")
                    ],
                    any_order=True,
                )

    def test_repeated_vector_queries_prepare_documents_once_and_print_each_ranking(
        self,
    ) -> None:
        fixtures = self.write_course_corpus()
        model, embeddings_by_input = self.make_vector_model(fixtures)
        embeddings_by_input[f"passage: 超时\n{fixtures['超时.md']}"] = np.asarray(
            [0.0, 1.0], dtype=np.float32
        )
        queries = ("请求超时", "怎样记录请求耗时？", "发送前怎样检查上下文长度？")
        query_vectors = ([0.0, 1.0], [1.0, 0.0], [-1.0, 0.0])
        arguments = ["--method", "vector", "--k", "2"]
        for query, vector in zip(queries, query_vectors):
            embeddings_by_input[f"query: {query}"] = np.asarray(
                vector, dtype=np.float32
            )
            arguments.extend(("--query", query))

        with patch(
            "sentence_transformers.SentenceTransformer", return_value=model
        ) as constructor:
            returncode, stdout, stderr = self.run_main(*arguments)

        self.assertEqual(returncode, 0, stderr)
        self.assertEqual(stderr, "")
        groups = re.findall(
            r"^查询 ([^\n]*)\n(.*?)(?=^查询 |\Z)",
            stdout,
            re.MULTILINE | re.DOTALL,
        )
        self.assertEqual([query for query, _ in groups], list(queries))
        expected = [
            [("超时.md", 1.0), ("日志.md", 0.0)],
            [("日志.md", 1.0), ("超时.md", 0.0)],
            [("预算.md", 1.0), ("超时.md", 0.0)],
        ]
        for (query, output), expected_results in zip(groups, expected):
            with self.subTest(query=query):
                self.assertEqual(
                    re.findall(r"^编号为 (\S+) 的文档", output, re.MULTILINE),
                    [doc_id for doc_id, _ in expected_results],
                )
                self.assertEqual(
                    [
                        float(score)
                        for score in re.findall(r"匹配得分：([^\s]+)", output)
                    ],
                    [score for _, score in expected_results],
                )
                for doc_id, _ in expected_results:
                    self.assertIn(fixtures[doc_id], output)
                    self.assertIn(f"标题是 {Path(doc_id).stem}，", output)
                    self.assertIn(f"来源是 {doc_id}，", output)

        constructor.assert_called_once()
        document_inputs = [
            text for text in embeddings_by_input if text.startswith("passage: ")
        ]
        self.assertEqual(model.encode.call_count, len(fixtures) + len(queries))
        self.assertCountEqual(
            model.encode.call_args_list[: len(fixtures)],
            [call(text, normalize_embeddings=True) for text in document_inputs],
        )
        self.assertEqual(
            model.encode.call_args_list[len(fixtures) :],
            [call(f"query: {query}", normalize_embeddings=True) for query in queries],
        )
        self.assertCountEqual(
            model.tokenizer.call_args_list,
            [call(text, truncation=False) for text in document_inputs],
        )

    def test_vector_query_batch_handles_blank_and_repeated_queries_independently(
        self,
    ) -> None:
        fixtures = self.write_course_corpus()
        model, embeddings_by_input = self.make_vector_model(fixtures)
        queries = ("请求超时", "", " \t", "请求超时")
        arguments = ["--method", "vector", "--k", "1"]
        for query in queries:
            arguments.extend(("--query", query))

        with patch(
            "sentence_transformers.SentenceTransformer", return_value=model
        ) as constructor:
            returncode, stdout, stderr = self.run_main(*arguments)

        self.assertEqual(returncode, 0, stderr)
        self.assertEqual(stderr, "")
        groups = re.findall(
            r"^查询 ([^\n]*)\n(.*?)(?=^查询 |\Z)",
            stdout,
            re.MULTILINE | re.DOTALL,
        )
        self.assertEqual([query for query, _ in groups], list(queries))
        self.assertEqual(groups[0][1], groups[3][1])
        self.assertEqual(
            re.findall(r"^编号为 (\S+) 的文档", groups[0][1], re.MULTILINE),
            ["日志.md"],
        )
        for _, output in groups[1:3]:
            self.assertEqual(output, "未找到匹配的文档\n")

        constructor.assert_called_once()
        self.assertEqual(model.encode.call_count, len(fixtures) + 2)
        self.assertCountEqual(
            model.encode.call_args_list[: len(fixtures)],
            [
                call(text, normalize_embeddings=True)
                for text in embeddings_by_input
                if text.startswith("passage: ")
            ],
        )
        self.assertEqual(
            model.encode.call_args_list[len(fixtures) :],
            [call("query: 请求超时", normalize_embeddings=True)] * 2,
        )
        self.assertEqual(model.tokenizer.call_count, len(fixtures))

    def test_vector_search_blank_queries_report_no_matches(self) -> None:
        fixtures = self.write_course_corpus()

        for query in ("", " \t\n"):
            with self.subTest(query=query):
                model, _ = self.make_vector_model(fixtures)
                with patch(
                    "sentence_transformers.SentenceTransformer", return_value=model
                ):
                    returncode, stdout, stderr = self.run_main(
                        "--query", query, "--method", "vector"
                    )

                self.assertEqual(returncode, 0, stderr)
                self.assertEqual(stdout.strip(), "未找到匹配的文档")
                self.assertEqual(stderr, "")
                self.assertEqual(
                    [
                        recorded
                        for recorded in model.encode.call_args_list
                        if recorded.args[0].startswith("query: ")
                    ],
                    [],
                )

    def test_vector_search_empty_corpus_reports_no_matches(self) -> None:
        model, _ = self.make_vector_model({})
        with patch("sentence_transformers.SentenceTransformer", return_value=model):
            returncode, stdout, stderr = self.run_main(
                "--query", "请求超时", "--method", "vector"
            )

        self.assertEqual(returncode, 0, stderr)
        self.assertEqual(stdout.strip(), "未找到匹配的文档")
        self.assertEqual(stderr, "")
        model.encode.assert_not_called()

    def test_vector_search_invalid_k_exits_before_query_encoding(self) -> None:
        fixtures = self.write_course_corpus()
        cases = (
            ("0", "k must be a positive integer"),
            ("-1", "k must be a positive integer"),
            ("1.5", "invalid int value"),
            ("abc", "invalid int value"),
        )

        for query in ("请求超时", ""):
            for k, message in cases:
                with self.subTest(query=query, k=k):
                    model, _ = self.make_vector_model(fixtures)
                    with patch(
                        "sentence_transformers.SentenceTransformer", return_value=model
                    ):
                        returncode, stdout, stderr = self.run_main(
                            "--query", query, "--method", "vector", "--k", k
                        )

                    self.assertEqual(returncode, 2)
                    self.assertIn(message, stderr)
                    self.assertNotIn("Traceback", stderr)
                    self.assertEqual(stdout, "")
                    self.assertEqual(
                        [
                            recorded
                            for recorded in model.encode.call_args_list
                            if recorded.args[0].startswith("query: ")
                        ],
                        [],
                    )

    def test_vector_search_document_validation_failure_stops_scoring(self) -> None:
        fixtures = self.write_course_corpus()
        document_input = f"passage: 预算\n{fixtures['预算.md']}"
        cases = (
            ([0.0, 0.0], "zero"),
            ([1.0, np.nan], "finite"),
            ([1.0, 0.0, 0.0], "dimension"),
        )

        for values, reason in cases:
            with self.subTest(values=values, reason=reason):
                model, embeddings_by_input = self.make_vector_model(fixtures)
                embeddings_by_input[document_input] = np.asarray(values)
                with (
                    patch(
                        "sentence_transformers.SentenceTransformer", return_value=model
                    ),
                    patch.object(
                        vector_retrieval, "cosine_similarity_unchecked"
                    ) as scorer,
                ):
                    returncode, stdout, stderr = self.run_main(
                        "--query", "请求超时", "--method", "vector"
                    )

                self.assertEqual(returncode, 2)
                self.assertIn(reason, stderr)
                self.assertNotIn("Traceback", stderr)
                self.assertEqual(stdout, "")
                self.assertIn(
                    call(document_input, normalize_embeddings=True),
                    model.encode.call_args_list,
                )
                self.assertEqual(
                    [
                        recorded
                        for recorded in model.encode.call_args_list
                        if recorded.args[0].startswith("query: ")
                    ],
                    [],
                )
                scorer.assert_not_called()

    def test_vector_search_query_validation_failure_stops_scoring(self) -> None:
        fixtures = self.write_course_corpus()
        cases = (
            ([0.0, 0.0], "zero"),
            ([1.0, np.nan], "finite"),
            ([1.0, 0.0, 0.0], "dimension"),
        )

        for values, reason in cases:
            with self.subTest(values=values, reason=reason):
                model, embeddings_by_input = self.make_vector_model(fixtures)
                embeddings_by_input["query: 请求超时"] = np.asarray(values)
                with (
                    patch(
                        "sentence_transformers.SentenceTransformer", return_value=model
                    ),
                    patch.object(
                        vector_retrieval, "cosine_similarity_unchecked"
                    ) as scorer,
                ):
                    returncode, stdout, stderr = self.run_main(
                        "--query", "请求超时", "--method", "vector"
                    )

                self.assertEqual(returncode, 2)
                self.assertIn(reason, stderr)
                self.assertNotIn("Traceback", stderr)
                self.assertEqual(stdout, "")
                self.assertEqual(model.encode.call_count, len(fixtures) + 1)
                self.assertEqual(
                    model.encode.call_args_list[-1],
                    call("query: 请求超时", normalize_embeddings=True),
                )
                scorer.assert_not_called()

    def test_keyword_search_uses_its_selected_method(self) -> None:
        self.write_course_corpus()
        with patch("sentence_transformers.SentenceTransformer") as constructor:
            returncode, stdout, stderr = self.run_main(
                "--query", "请求超时", "--method", "keyword"
            )

        self.assertEqual(returncode, 0, stderr)
        self.assertEqual(stderr, "")
        self.assertEqual(
            re.findall(r"^编号为 (\S+) 的文档", stdout, re.MULTILINE),
            ["超时.md", "日志.md"],
        )
        constructor.assert_not_called()

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

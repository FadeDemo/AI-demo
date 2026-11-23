"""通过命令行入口验证文档加载、检索、批量评测、输出和退出状态。"""

import json
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
from rag_knowledge_base import cli, evaluation, vector_retrieval
from rag_knowledge_base.cli import main

CHUNK_SOURCE_PATTERN = r"来源是 ([^，\n]+)，匹配得分：[^，\n]+，区间是 "


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

    def write_evaluation_queries(self) -> Path:
        queries = [
            {
                "query_id": "q01",
                "text": "请求超时",
                "relevant_doc_ids": ["超时.md"],
            },
            {
                "query_id": "q02",
                "text": "预算",
                "relevant_doc_ids": ["预算.md"],
            },
            {"query_id": "q03", "text": "火山", "relevant_doc_ids": []},
        ]
        path = self.working_directory / "queries.json"
        path.write_text(json.dumps(queries, ensure_ascii=False), encoding="utf-8")
        return path

    def assert_evaluation_output(
        self,
        stdout: str,
        rankings: list[list[tuple[str, float]]],
        metrics: list[tuple[int, float | None, float, float | None]],
    ) -> None:
        groups = re.findall(
            r"^问题编号是 (\S+)，检索结果是\n(.*?)(?=^问题编号是 |^有答案的问题数量是 |\Z)",
            stdout,
            re.MULTILINE | re.DOTALL,
        )
        self.assertEqual([query_id for query_id, _ in groups], ["q01", "q02", "q03"])
        for (query_id, output), ranking, metric in zip(
            groups, rankings, metrics, strict=True
        ):
            with self.subTest(query_id=query_id):
                self.assertEqual(
                    re.findall(r"^编号为 (\S+) 的文档", output, re.MULTILINE),
                    [doc_id for doc_id, _ in ranking],
                )
                self.assertEqual(
                    [
                        float(score)
                        for score in re.findall(r"匹配得分：([^\s]+)", output)
                    ],
                    [score for _, score in ranking],
                )
                hit_count, recall, precision, rr = metric
                self.assertIn(
                    f"命中数是 {hit_count}，recall是 {recall}，"
                    f"precision是 {precision}，rr是 {rr}",
                    output,
                )
                self.assertRegex(output, r"(?m)^耗时是 [0-9.e+-]+$")
                if not ranking:
                    self.assertIn("未找到匹配的文档", output)
        self.assertIn("有答案的问题数量是 2，无答案的问题数量是 1，", stdout)
        self.assertRegex(stdout, r"(?m)^准备耗时是 [0-9.e+-]+$")

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
        self.assertIn("--evaluate", result.stdout)
        self.assertIn("评测问题文件", result.stdout)
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

    def test_keyword_search_prints_course_ranking_and_chunk_fields(self) -> None:
        fixtures = self.write_course_corpus()

        result = self.run_cli(
            "docs", "--query", "请求超时", "--method", "keyword", "--k", "5"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertNotRegex(result.stdout, r"(?m)^查询 ")
        self.assertEqual(
            re.findall(CHUNK_SOURCE_PATTERN, result.stdout),
            ["超时.md", "日志.md"],
        )
        for doc_id, score in (("超时.md", 3), ("日志.md", 2)):
            with self.subTest(doc_id=doc_id):
                self.assertIn(f"标题是 {Path(doc_id).stem}，", result.stdout)
                self.assertIn(fixtures[doc_id], result.stdout)
                self.assertIn(
                    f"来源是 {doc_id}，匹配得分：{score}，区间是 [0, {len(fixtures[doc_id])})",
                    result.stdout,
                )
        self.assertNotIn("预算.md", result.stdout)

    def test_keyword_search_returns_two_chunks_with_their_source_slices(self) -> None:
        body = "开头。" * 27 + "重试。" + "后续说明。" * 8
        (self.corpus_root / "guide.md").write_text(f"  {body}\n", encoding="utf-8")

        result = self.run_cli(
            "docs", "--query", "重试", "--method", "keyword", "--k", "2"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        matches = re.findall(
            r"^编号为 (.+?) 的chunk，标题是 guide，内容是 (.+)，来源是 guide\.md，"
            r"匹配得分：1，区间是 \[(\d+), (\d+)\)$",
            result.stdout,
            re.MULTILINE,
        )
        self.assertEqual(
            [(int(start), int(end), text) for _, text, start, end in matches],
            [(0, 100, body[:100]), (80, len(body), body[80:])],
        )
        self.assertEqual(len({chunk_id for chunk_id, _, _, _ in matches}), 2)

    def test_repeated_keyword_queries_print_independent_result_groups(self) -> None:
        fixtures = self.write_course_corpus()
        queries = ("请求超时", "", "预算", "火山", "日志", "请求超时")
        arguments = ["--method", "keyword", "--k", "1"]
        for query in queries:
            arguments.extend(("--query", query))

        with patch.object(cli, "prepare_chunks", wraps=cli.prepare_chunks) as prepare:
            returncode, stdout, stderr = self.run_main(*arguments)

        self.assertEqual(returncode, 0, stderr)
        self.assertEqual(stderr, "")
        prepare.assert_called_once()
        groups = re.findall(
            r"^查询 ([^\n]*)\n(.*?)(?=^查询 |\Z)",
            stdout,
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
                    re.findall(CHUNK_SOURCE_PATTERN, output),
                    [doc_id for doc_id, _ in expected_results],
                )
                self.assertEqual(
                    re.findall(r"匹配得分：(\d+)，区间是 ", output),
                    [str(score) for _, score in expected_results],
                )
                for doc_id, _ in expected_results:
                    self.assertIn(fixtures[doc_id], output)
                    self.assertIn(f"标题是 {Path(doc_id).stem}，", output)
                    self.assertIn(f"来源是 {doc_id}，", output)
                if not expected_results:
                    self.assertEqual(output, "未找到匹配的chunk\n")

    def test_search_defaults_to_keyword_and_five_results_with_stable_ties(self) -> None:
        for name in ("f", "e", "d", "c", "b", "a"):
            (self.corpus_root / f"{name}.md").write_text("发生超时。", encoding="utf-8")

        result = self.run_cli("docs", "--query", "超时")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            re.findall(CHUNK_SOURCE_PATTERN, result.stdout),
            ["a.md", "b.md", "c.md", "d.md", "e.md"],
        )
        self.assertEqual(result.stdout.count("匹配得分：1"), 5)

    def test_keyword_search_k_one_returns_only_the_highest_scoring_chunk(self) -> None:
        self.write_course_corpus()

        result = self.run_cli("docs", "--query", "请求超时", "--k", "1")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            re.findall(CHUNK_SOURCE_PATTERN, result.stdout),
            ["超时.md"],
        )
        self.assertIn("来源是 超时.md，匹配得分：3", result.stdout)

    def test_search_empty_or_unmatched_queries_report_no_matches(self) -> None:
        self.write_course_corpus()

        for query in ("", " \t\n", "，！？", "火山"):
            with self.subTest(query=query):
                result = self.run_cli("docs", "--query", query)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "未找到匹配的chunk")
                self.assertEqual(result.stderr, "")

    def test_search_empty_corpus_reports_no_matches(self) -> None:
        result = self.run_cli("docs", "--query", "请求超时")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "未找到匹配的chunk")
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

    def test_vector_search_encodes_and_prints_ranked_chunks(self) -> None:
        fixtures = self.write_course_corpus()
        log_body = fixtures["日志.md"] + "\n\n" + "记录耗时和结束原因。" * 12
        (self.corpus_root / "日志.md").write_text(f"  {log_body}\n", encoding="utf-8")
        bodies_by_source = {**fixtures, "日志.md": log_body}
        expected = [
            ("日志.md", 0, 100, 1.0),
            ("日志.md", 80, len(log_body), 1.0),
            ("超时.md", 0, len(fixtures["超时.md"]), 1.0),
            ("预算.md", 0, len(fixtures["预算.md"]), -1.0),
        ]
        expected_cache = Path(__file__).resolve().parents[3] / ".cache" / "huggingface"

        for k in (1, 2, 5):
            with self.subTest(k=k):
                model, embeddings_by_input = self.make_vector_model(fixtures)
                log_vector = embeddings_by_input.pop(
                    f"passage: 日志\n{fixtures['日志.md']}"
                )
                embeddings_by_input[f"passage: 日志\n{log_body[:100]}"] = log_vector
                embeddings_by_input[f"passage: 日志\n{log_body[80:]}"] = log_vector
                with patch(
                    "sentence_transformers.SentenceTransformer", return_value=model
                ) as constructor:
                    returncode, stdout, stderr = self.run_main(
                        "--query", "请求超时", "--method", "vector", "--k", str(k)
                    )

                self.assertEqual(returncode, 0, stderr)
                self.assertEqual(stderr, "")
                self.assertNotRegex(stdout, r"(?m)^查询 ")
                displayed_chunks = re.findall(
                    r"^编号为 (.+?) 的chunk，(.*?)(?=\n编号为 |\n\Z)",
                    stdout,
                    re.MULTILINE | re.DOTALL,
                )
                self.assertEqual(
                    [details for _, details in displayed_chunks],
                    [
                        f"标题是 {Path(source).stem}，"
                        f"内容是 {bodies_by_source[source][start:end]}，来源是 {source}，"
                        f"匹配得分：{score}，区间是 [{start}, {end})"
                        for source, start, end, score in expected[:k]
                    ],
                )
                self.assertEqual(
                    len({chunk_id for chunk_id, _ in displayed_chunks}),
                    len(expected[:k]),
                )

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
                self.assertEqual(model.encode.call_count, len(embeddings_by_input))
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
                self.assertCountEqual(
                    model.tokenizer.call_args_list,
                    [
                        call(text, truncation=False)
                        for text in embeddings_by_input
                        if text.startswith("passage: ")
                    ],
                )

    def test_repeated_vector_queries_prepare_chunks_once_and_print_each_ranking(
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

        with (
            patch(
                "sentence_transformers.SentenceTransformer", return_value=model
            ) as constructor,
            patch.object(cli, "prepare_chunks", wraps=cli.prepare_chunks) as prepare,
        ):
            returncode, stdout, stderr = self.run_main(*arguments)

        self.assertEqual(returncode, 0, stderr)
        self.assertEqual(stderr, "")
        prepare.assert_called_once()
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
                    re.findall(CHUNK_SOURCE_PATTERN, output),
                    [doc_id for doc_id, _ in expected_results],
                )
                self.assertEqual(
                    [
                        float(score)
                        for score in re.findall(
                            r"匹配得分：([^，\n]+)，区间是 ", output
                        )
                    ],
                    [score for _, score in expected_results],
                )
                for doc_id, _ in expected_results:
                    self.assertIn(fixtures[doc_id], output)
                    self.assertIn(f"标题是 {Path(doc_id).stem}，", output)
                    self.assertIn(f"来源是 {doc_id}，", output)

        constructor.assert_called_once()
        chunk_inputs = [
            text for text in embeddings_by_input if text.startswith("passage: ")
        ]
        self.assertEqual(model.encode.call_count, len(chunk_inputs) + len(queries))
        self.assertCountEqual(
            model.encode.call_args_list[: len(chunk_inputs)],
            [call(text, normalize_embeddings=True) for text in chunk_inputs],
        )
        self.assertEqual(
            model.encode.call_args_list[len(chunk_inputs) :],
            [call(f"query: {query}", normalize_embeddings=True) for query in queries],
        )
        self.assertCountEqual(
            model.tokenizer.call_args_list,
            [call(text, truncation=False) for text in chunk_inputs],
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
            re.findall(CHUNK_SOURCE_PATTERN, groups[0][1]),
            ["日志.md"],
        )
        for _, output in groups[1:3]:
            self.assertEqual(output, "未找到匹配的chunk\n")

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
                self.assertEqual(stdout.strip(), "未找到匹配的chunk")
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
        self.assertEqual(stdout.strip(), "未找到匹配的chunk")
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

    def test_vector_search_rejects_overlong_chunk_input_before_encoding(self) -> None:
        body = "请求超时后有限重试。" * 12
        (self.corpus_root / "guide.md").write_text(body, encoding="utf-8")
        model, _ = self.make_vector_model({})
        model.max_seq_length = 3
        model.tokenizer.return_value = {"input_ids": [101, 5, 6, 102]}

        with patch("sentence_transformers.SentenceTransformer", return_value=model):
            returncode, stdout, stderr = self.run_main(
                "--query", "请求超时", "--method", "vector"
            )

        self.assertEqual(returncode, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Chunk ", stderr)
        self.assertIn("guide.md", stderr)
        self.assertIn("is too long: 4 > 3", stderr)
        self.assertNotIn("Traceback", stderr)
        model.tokenizer.assert_called_once_with(
            f"passage: guide\n{body[:100]}", truncation=False
        )
        model.encode.assert_not_called()

    def test_vector_search_chunk_validation_failure_stops_scoring(self) -> None:
        fixtures = self.write_course_corpus()
        chunk_input = f"passage: 预算\n{fixtures['预算.md']}"
        cases = (
            ([0.0, 0.0], "zero"),
            ([1.0, np.nan], "finite"),
            ([1.0, 0.0, 0.0], "dimension"),
        )

        for values, reason in cases:
            with self.subTest(values=values, reason=reason):
                model, embeddings_by_input = self.make_vector_model(fixtures)
                embeddings_by_input[chunk_input] = np.asarray(values)
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
                    call(chunk_input, normalize_embeddings=True),
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
            re.findall(CHUNK_SOURCE_PATTERN, stdout),
            ["超时.md", "日志.md"],
        )
        constructor.assert_not_called()

    def test_keyword_evaluation_prints_rankings_metrics_and_summary(self) -> None:
        self.write_course_corpus()
        queries_path = self.write_evaluation_queries()

        for k in (1, 3, 5):
            with self.subTest(k=k):
                arguments = ["--evaluate", str(queries_path)]
                if k != 5:
                    arguments.extend(("--method", "keyword", "--k", str(k)))
                with patch("sentence_transformers.SentenceTransformer") as constructor:
                    returncode, stdout, stderr = self.run_main(*arguments)

                self.assertEqual(returncode, 0, stderr)
                self.assertEqual(stderr, "")
                self.assert_evaluation_output(
                    stdout,
                    [
                        [("超时.md", 3), ("日志.md", 2)][:k],
                        [("预算.md", 1)],
                        [],
                    ],
                    [
                        (1, 1.0, 1 / k, 1.0),
                        (1, 1.0, 1 / k, 1.0),
                        (0, None, 0.0, None),
                    ],
                )
                self.assertIn(
                    f"平均recall是 1.0，平均precision是 {1 / k}，mrr是 1.0",
                    stdout,
                )
                constructor.assert_not_called()

    def test_vector_evaluation_prepares_once_and_prints_each_query_result(self) -> None:
        fixtures = self.write_course_corpus()
        queries_path = self.write_evaluation_queries()

        for k in (1, 3, 5):
            with self.subTest(k=k):
                model, embeddings_by_input = self.make_vector_model(fixtures)
                embeddings_by_input["query: 预算"] = np.asarray([-1.0, 0.0])
                embeddings_by_input["query: 火山"] = np.asarray([0.0, 1.0])
                with patch(
                    "sentence_transformers.SentenceTransformer", return_value=model
                ) as constructor:
                    returncode, stdout, stderr = self.run_main(
                        "--evaluate",
                        str(queries_path),
                        "--method",
                        "vector",
                        "--k",
                        str(k),
                    )

                first_metrics = (1, 1.0, 1 / k, 0.5)
                mean_recall, mean_precision, mrr = 1.0, 1 / k, 0.75
                if k == 1:
                    first_metrics = (0, 0.0, 0.0, 0.0)
                    mean_recall, mean_precision, mrr = 0.5, 0.5, 0.5
                self.assertEqual(returncode, 0, stderr)
                self.assertEqual(stderr, "")
                self.assert_evaluation_output(
                    stdout,
                    [
                        [("日志.md", 1.0), ("超时.md", 1.0), ("预算.md", -1.0)][:k],
                        [("预算.md", 1.0), ("日志.md", -1.0), ("超时.md", -1.0)][:k],
                        [("日志.md", 0.0), ("超时.md", 0.0), ("预算.md", 0.0)][:k],
                    ],
                    [first_metrics, (1, 1.0, 1 / k, 1.0), (0, None, 0.0, None)],
                )
                self.assertIn(
                    f"平均recall是 {mean_recall}，"
                    f"平均precision是 {mean_precision}，mrr是 {mrr}",
                    stdout,
                )
                constructor.assert_called_once()
                self.assertEqual(model.encode.call_count, len(fixtures) + 3)
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
                    [
                        call(f"query: {text}", normalize_embeddings=True)
                        for text in ("请求超时", "预算", "火山")
                    ],
                )
                self.assertEqual(model.tokenizer.call_count, len(fixtures))

    def test_evaluation_preparation_timer_includes_loading_and_stops_before_queries(
        self,
    ) -> None:
        fixtures = self.write_course_corpus()
        queries_path = self.write_evaluation_queries()

        for method in ("keyword", "vector"):
            with self.subTest(method=method):
                model, embeddings_by_input = self.make_vector_model(fixtures)
                embeddings_by_input["query: 预算"] = np.asarray([-1.0, 0.0])
                embeddings_by_input["query: 火山"] = np.asarray([0.0, 1.0])
                tracked = Mock()
                tracked.clock.side_effect = [
                    10.0,
                    20.0,
                    30.0,
                    30.25,
                    40.0,
                    40.5,
                    50.0,
                    50.75,
                ]
                tracked.load_documents.side_effect = cli.load_documents
                tracked.load_queries.side_effect = evaluation.load_evaluation_queries
                batch_name = f"evaluate_{method}_queries"
                tracked.batch.side_effect = getattr(evaluation, batch_name)
                tracked.constructor.return_value = model
                tracked.attach_mock(model.encode, "encode")
                with (
                    patch.object(cli.time, "perf_counter", tracked.clock),
                    patch.object(cli, "load_documents", tracked.load_documents),
                    patch.object(
                        evaluation, "load_evaluation_queries", tracked.load_queries
                    ),
                    patch.object(evaluation, batch_name, tracked.batch),
                    patch(
                        "sentence_transformers.SentenceTransformer", tracked.constructor
                    ),
                ):
                    returncode, stdout, stderr = self.run_main(
                        "--evaluate", str(queries_path), "--method", method
                    )

                self.assertEqual(returncode, 0, stderr)
                self.assertEqual(stderr, "")
                self.assertIn("准备耗时是 10.0", stdout)
                self.assertEqual(
                    re.findall(r"^耗时是 (\S+)$", stdout, re.MULTILINE),
                    ["0.25", "0.5", "0.75"],
                )
                names = [entry[0] for entry in tracked.mock_calls]
                clocks = [index for index, name in enumerate(names) if name == "clock"]
                self.assertLess(clocks[0], names.index("load_documents"))
                self.assertLess(
                    names.index("load_documents"), names.index("load_queries")
                )
                self.assertLess(names.index("load_queries"), clocks[1])
                self.assertLess(clocks[1], names.index("batch"))
                tracked.load_documents.assert_called_once()
                tracked.load_queries.assert_called_once()
                tracked.batch.assert_called_once()
                if method == "vector":
                    self.assertLess(names.index("constructor"), clocks[1])
                    encodings = [
                        index for index, name in enumerate(names) if name == "encode"
                    ]
                    self.assertLess(encodings[len(fixtures) - 1], clocks[1])
                    self.assertGreater(encodings[len(fixtures)], names.index("batch"))

    def test_evaluation_is_mutually_exclusive_with_query_and_document_lookup(
        self,
    ) -> None:
        queries_path = self.write_evaluation_queries()
        for option, value in (("--query", "请求超时"), ("--doc-id", "超时.md")):
            for arguments in (
                ("--evaluate", str(queries_path), option, value),
                (option, value, "--evaluate", str(queries_path)),
            ):
                with self.subTest(arguments=arguments):
                    returncode, stdout, stderr = self.run_main(*arguments)

                    self.assertEqual(returncode, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn("not allowed with argument", stderr)
                    self.assertIn("--evaluate", stderr)
                    self.assertIn(option, stderr)

    def test_evaluation_rejects_invalid_k_before_loading(self) -> None:
        queries_path = self.write_evaluation_queries()
        for method in ("keyword", "vector"):
            for k in ("0", "-1", "1.5", "abc"):
                with self.subTest(method=method, k=k):
                    with patch.object(cli, "load_documents") as loader:
                        returncode, stdout, stderr = self.run_main(
                            "--evaluate",
                            str(queries_path),
                            "--method",
                            method,
                            "--k",
                            k,
                        )

                    self.assertEqual(returncode, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn("error:", stderr)
                    self.assertNotIn("Traceback", stderr)
                    loader.assert_not_called()

    def test_evaluation_annotation_errors_report_to_stderr_and_exit(self) -> None:
        self.write_course_corpus()
        queries_path = self.working_directory / "queries.json"
        invalid_queries = {"query_id": "q01", "text": "请求超时"}
        cases = (
            (None, "Queries file not found"),
            ("{", "Expecting property name"),
            (json.dumps([invalid_queries]), "Relevant document IDs are required"),
            (
                json.dumps([{**invalid_queries, "relevant_doc_ids": ["missing.md"]}]),
                "document ID not found",
            ),
            (json.dumps([{"query_id": "q01", "relevant_doc_ids": []}]), "'text'"),
            (json.dumps([None]), "not subscriptable"),
        )
        for content, message in cases:
            with self.subTest(message=message):
                if content is not None:
                    queries_path.write_text(content, encoding="utf-8")
                returncode, stdout, stderr = self.run_main(
                    "--evaluate", str(queries_path)
                )

                self.assertEqual(returncode, 2)
                self.assertEqual(stdout, "")
                self.assertIn(message, stderr)
                self.assertNotIn("Traceback", stderr)

    def test_evaluation_runtime_failures_report_to_stderr_and_exit(self) -> None:
        fixtures = self.write_course_corpus()
        queries_path = self.write_evaluation_queries()
        message = "evaluation-runtime-failure"
        for method, phase, error_type in (
            ("keyword", "search", RuntimeError),
            ("vector", "model", RuntimeError),
            ("vector", "model", ImportError),
            ("vector", "query", RuntimeError),
        ):
            with self.subTest(method=method, phase=phase, error_type=error_type):
                model, _ = self.make_vector_model(fixtures)
                model.encode.side_effect = [
                    np.asarray([1.0, 0.0]) for _ in fixtures
                ] + [RuntimeError(message)]
                with (
                    patch(
                        "sentence_transformers.SentenceTransformer", return_value=model
                    ) as constructor,
                    patch.object(
                        evaluation, "search_keywords", side_effect=RuntimeError(message)
                    ) as keyword_search,
                ):
                    if phase == "model":
                        constructor.side_effect = error_type(message)
                    returncode, stdout, stderr = self.run_main(
                        "--evaluate", str(queries_path), "--method", method
                    )

                self.assertEqual(returncode, 2)
                self.assertEqual(stdout, "")
                self.assertIn(message, stderr)
                self.assertNotIn("Traceback", stderr)
                if method == "keyword":
                    keyword_search.assert_called_once()
                    constructor.assert_not_called()
                else:
                    constructor.assert_called_once()
                    keyword_search.assert_not_called()
                    if phase == "query":
                        self.assertEqual(model.encode.call_count, len(fixtures) + 1)
                        self.assertEqual(
                            model.encode.call_args_list[-1],
                            call("query: 请求超时", normalize_embeddings=True),
                        )

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

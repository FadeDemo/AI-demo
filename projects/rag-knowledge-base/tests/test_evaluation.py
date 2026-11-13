"""验证评测问题读取、单题指标计算和编号校验。"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from rag_knowledge_base.document import Document
from rag_knowledge_base.evaluation import (
    EvaluationQuery,
    QueryMetrics,
    calculate_query_metrics,
    load_evaluation_queries,
)


class EvaluationQueryLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        temporary_root = repository_root / ".agent-tmp"
        if temporary_root.is_symlink() or not temporary_root.resolve().is_relative_to(
            repository_root
        ):
            raise RuntimeError("Test temporary files must stay in the repository")
        temporary_root.mkdir(exist_ok=True)
        directory = TemporaryDirectory(
            prefix="evaluation-loader-test-", dir=temporary_root
        )
        self.addCleanup(directory.cleanup)
        self.queries_path = Path(directory.name) / "queries.json"
        self.documents = [
            Document("超时.md", "超时", "请求超时后有限重试。", "超时.md"),
            Document(
                "requests/retry-limit.md",
                "重试次数",
                "首次发送也计入最大尝试次数。",
                "requests/retry-limit.md",
            ),
        ]
        self.query = {
            "query_id": "q01",
            "text": "请求超时后怎样限制重试？",
            "relevant_doc_ids": ["超时.md"],
        }

    def write_queries(self, queries: list[dict[str, object]]) -> None:
        self.queries_path.write_text(
            json.dumps(queries, ensure_ascii=False), encoding="utf-8"
        )

    def test_returns_one_object_per_query_and_preserves_unanswerable_queries(
        self,
    ) -> None:
        self.write_queries(
            [
                {
                    "query_id": "q02",
                    "text": "请求超时后怎样限制重试？",
                    "relevant_doc_ids": ["超时.md", "requests/retry-limit.md"],
                    "category": "common",
                },
                {
                    "query_id": "q01",
                    "text": "本服务每分钟允许发送多少次请求？",
                    "relevant_doc_ids": [],
                    "unanswerable_reason": "语料没有记录具体限额。",
                },
            ]
        )

        results = load_evaluation_queries(self.queries_path, self.documents)

        self.assertEqual(
            results,
            [
                EvaluationQuery(
                    query_id="q02",
                    text="请求超时后怎样限制重试？",
                    relevant_doc_ids=["超时.md", "requests/retry-limit.md"],
                ),
                EvaluationQuery(
                    query_id="q01",
                    text="本服务每分钟允许发送多少次请求？",
                    relevant_doc_ids=[],
                ),
            ],
        )

    def test_duplicate_query_ids_raise(self) -> None:
        self.write_queries([self.query, self.query])

        with self.assertRaisesRegex(ValueError, "Duplicate query ID: q01"):
            load_evaluation_queries(self.queries_path, self.documents)

    def test_duplicate_relevant_document_ids_raise(self) -> None:
        self.query["relevant_doc_ids"] = ["超时.md", "超时.md"]
        self.write_queries([self.query])

        with self.assertRaisesRegex(ValueError, "Duplicate relevant document ID: 超时"):
            load_evaluation_queries(self.queries_path, self.documents)

    def test_unknown_relevant_document_id_raises(self) -> None:
        self.query["relevant_doc_ids"] = ["missing.md"]
        self.write_queries([self.query])

        with self.assertRaisesRegex(ValueError, "document ID not found: missing"):
            load_evaluation_queries(self.queries_path, self.documents)

    def test_missing_or_null_annotation_raises_with_query_id(self) -> None:
        for annotation in ({}, {"relevant_doc_ids": None}):
            with self.subTest(annotation=annotation):
                query = {
                    "query_id": "q01",
                    "text": "请求超时后怎样限制重试？",
                    **annotation,
                }
                self.write_queries([query])

                with self.assertRaisesRegex(
                    ValueError, "Relevant document IDs are required for query: q01"
                ):
                    load_evaluation_queries(self.queries_path, self.documents)


class QueryMetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.query = EvaluationQuery("q01", "示例问题", ["B", "D"])
        self.unanswerable_query = EvaluationQuery("q02", "无答案问题", [])
        self.valid_doc_ids = set("ABCDE")

    def test_calculates_course_ranking_at_each_cutoff(self) -> None:
        cases = (
            (1, QueryMetrics(0, 0.0, 0.0, 0.0)),
            (3, QueryMetrics(1, 1 / 2, 1 / 3, 1 / 2)),
            (5, QueryMetrics(2, 1.0, 2 / 5, 1 / 2)),
        )

        for k, expected in cases:
            with self.subTest(k=k):
                result = calculate_query_metrics(
                    self.query, list("ABCDE"), k, self.valid_doc_ids
                )

                self.assertEqual(result, expected)

    def test_precision_uses_k_when_fewer_results_are_returned(self) -> None:
        result = calculate_query_metrics(self.query, ["B"], 3, self.valid_doc_ids)

        self.assertEqual(result, QueryMetrics(1, 1 / 2, 1 / 3, 1.0))

    def test_answerable_query_without_a_top_k_hit_has_zero_scores(self) -> None:
        for ranking in ([], ["A", "C"], ["A", "C", "B"]):
            with self.subTest(ranking=ranking):
                result = calculate_query_metrics(
                    self.query, ranking, 2, self.valid_doc_ids
                )

                self.assertEqual(result, QueryMetrics(0, 0.0, 0.0, 0.0))

    def test_unanswerable_query_has_inapplicable_recall_and_rr(self) -> None:
        for ranking in ([], list("ABCDE")):
            with self.subTest(ranking=ranking):
                result = calculate_query_metrics(
                    self.unanswerable_query, ranking, 3, self.valid_doc_ids
                )

                self.assertEqual(result, QueryMetrics(0, None, 0.0, None))

    def test_invalid_k_raises_even_with_an_empty_ranking(self) -> None:
        cases = (
            (0, ValueError),
            (-1, ValueError),
            (1.0, TypeError),
            (1.5, TypeError),
            (True, TypeError),
            (False, TypeError),
            ("3", TypeError),
            (None, TypeError),
        )

        for k, error_type in cases:
            with self.subTest(k=k), self.assertRaises(error_type):
                calculate_query_metrics(self.query, [], k, self.valid_doc_ids)

    def test_duplicate_ranked_ids_raise_including_beyond_k(self) -> None:
        for query in (self.query, self.unanswerable_query):
            for ranking in (["A", "A"], ["A", "B", "A"], ["A", "B", "C", "C"]):
                with (
                    self.subTest(query_id=query.query_id, ranking=ranking),
                    self.assertRaisesRegex(ValueError, "Duplicate ranked document ID"),
                ):
                    calculate_query_metrics(query, ranking, 2, self.valid_doc_ids)

    def test_unknown_ranked_ids_raise_including_beyond_k(self) -> None:
        for query in (self.query, self.unanswerable_query):
            for ranking in (["X"], ["A", "B", "X"]):
                with (
                    self.subTest(query_id=query.query_id, ranking=ranking),
                    self.assertRaisesRegex(ValueError, "Ranked document ID not found"),
                ):
                    calculate_query_metrics(query, ranking, 2, self.valid_doc_ids)


if __name__ == "__main__":
    unittest.main()

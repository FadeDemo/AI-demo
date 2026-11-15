"""验证评测材料、指标汇总和两种检索的批量评测流程。"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, call, patch

import numpy as np
from rag_knowledge_base import evaluation
from rag_knowledge_base.document import Document
from rag_knowledge_base.evaluation import (
    EvaluationQuery,
    EvaluationSummary,
    QueryEvaluation,
    QueryMetrics,
    calculate_query_metrics,
    evaluate_keyword_queries,
    evaluate_vector_queries,
    load_evaluation_queries,
    summarize_query_metrics,
)
from rag_knowledge_base.keyword_retrieval import search_keywords
from rag_knowledge_base.vector_retrieval import search_vectors


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


class EvaluationSummaryTests(unittest.TestCase):
    def test_counts_queries_and_excludes_unanswerable_scores_from_all_means(
        self,
    ) -> None:
        metrics = [
            QueryMetrics(1, 1 / 2, 1 / 3, 1 / 2),
            QueryMetrics(0, 0.0, 0.0, 0.0),
            QueryMetrics(0, None, 0.0, None),
        ]

        result = summarize_query_metrics(metrics)

        self.assertEqual(result, EvaluationSummary(2, 1, 1 / 4, 1 / 6, 1 / 4))

    def test_averages_queries_with_equal_weight(self) -> None:
        metrics = [
            QueryMetrics(1, 1.0, 1 / 3, 1.0),
            QueryMetrics(1, 1 / 3, 1 / 3, 1 / 3),
        ]

        result = summarize_query_metrics(metrics)

        self.assertEqual(result.answerable_count, 2)
        self.assertEqual(result.unanswerable_count, 0)
        self.assertAlmostEqual(result.mean_recall, 2 / 3)
        self.assertAlmostEqual(result.mean_precision, 1 / 3)
        self.assertAlmostEqual(result.mrr, 2 / 3)

    def test_zero_scoring_answerable_queries_have_zero_means(self) -> None:
        metrics = [
            QueryMetrics(0, 0.0, 0.0, 0.0),
            QueryMetrics(0, None, 0.0, None),
        ]

        result = summarize_query_metrics(metrics)

        self.assertEqual(result, EvaluationSummary(1, 1, 0.0, 0.0, 0.0))

    def test_all_unanswerable_queries_have_inapplicable_means(self) -> None:
        metrics = [
            QueryMetrics(0, None, 0.0, None),
            QueryMetrics(0, None, 0.0, None),
        ]

        result = summarize_query_metrics(metrics)

        self.assertEqual(result, EvaluationSummary(0, 2, None, None, None))

    def test_empty_input_has_zero_counts_and_inapplicable_means(self) -> None:
        result = summarize_query_metrics([])

        self.assertEqual(result, EvaluationSummary(0, 0, None, None, None))


class KeywordEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.budget = Document("预算.md", "预算", "发送前检查上下文长度。", "预算.md")
        self.log = Document("日志.md", "日志", "记录请求耗时与超时类别。", "日志.md")
        self.timeout = Document("超时.md", "超时", "请求超时后有限重试。", "超时.md")
        self.documents = [self.budget, self.log, self.timeout]
        self.queries = [
            EvaluationQuery("q02", "请求超时", ["超时.md", "日志.md"]),
            EvaluationQuery("q01", "上下文", ["预算.md"]),
            EvaluationQuery("q03", "火山", []),
            EvaluationQuery("q04", "请求超时上限是多少", []),
        ]

    def test_runs_real_keyword_search_metrics_and_summary_for_every_query(self) -> None:
        with patch.object(
            evaluation.time,
            "perf_counter",
            side_effect=[10.0, 10.25, 20.0, 20.5, 30.0, 30.75, 40.0, 41.0],
        ):
            records, summary = evaluate_keyword_queries(self.documents, self.queries, 3)

        self.assertEqual(
            records,
            [
                QueryEvaluation(
                    query=self.queries[0],
                    search_results=[(self.timeout, 3), (self.log, 2)],
                    metrics=QueryMetrics(2, 1.0, 2 / 3, 1.0),
                    elapsed_seconds=0.25,
                ),
                QueryEvaluation(
                    query=self.queries[1],
                    search_results=[(self.budget, 2)],
                    metrics=QueryMetrics(1, 1.0, 1 / 3, 1.0),
                    elapsed_seconds=0.5,
                ),
                QueryEvaluation(
                    query=self.queries[2],
                    search_results=[],
                    metrics=QueryMetrics(0, None, 0.0, None),
                    elapsed_seconds=0.75,
                ),
                QueryEvaluation(
                    query=self.queries[3],
                    search_results=[(self.timeout, 3), (self.log, 2)],
                    metrics=QueryMetrics(0, None, 0.0, None),
                    elapsed_seconds=1.0,
                ),
            ],
        )
        self.assertEqual(summary, EvaluationSummary(2, 2, 1.0, 0.5, 1.0))

    def test_passes_k_to_both_search_and_metrics(self) -> None:
        records, summary = evaluate_keyword_queries(self.documents, self.queries[:1], 1)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].search_results, [(self.timeout, 3)])
        self.assertEqual(records[0].metrics, QueryMetrics(1, 0.5, 1.0, 1.0))
        self.assertEqual(summary, EvaluationSummary(1, 0, 0.5, 1.0, 1.0))

    def test_empty_batch_returns_empty_records_and_summary(self) -> None:
        records, summary = evaluate_keyword_queries(self.documents, [], 3)

        self.assertEqual(records, [])
        self.assertEqual(summary, EvaluationSummary(0, 0, None, None, None))

    def test_invalid_k_is_rejected_before_search_even_for_an_empty_batch(self) -> None:
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

        with patch.object(evaluation, "search_keywords") as search:
            for queries in ([], self.queries):
                for k, error_type in cases:
                    with (
                        self.subTest(query_count=len(queries), k=k),
                        self.assertRaises(error_type),
                    ):
                        evaluate_keyword_queries(self.documents, queries, k)
            search.assert_not_called()

    def test_search_and_metric_errors_propagate(self) -> None:
        for dependency in ("search_keywords", "calculate_query_metrics"):
            error = RuntimeError(f"simulated {dependency} failure")
            with (
                self.subTest(dependency=dependency),
                patch.object(evaluation, dependency, side_effect=error) as failing_call,
                self.assertRaises(RuntimeError) as caught,
            ):
                evaluate_keyword_queries(self.documents, self.queries, 3)

            self.assertIs(caught.exception, error)
            failing_call.assert_called_once()

    def test_times_search_before_metric_calculation_and_summary(self) -> None:
        tracked = Mock()
        tracked.clock.side_effect = [10.0, 10.25]
        tracked.search.side_effect = search_keywords
        tracked.metrics.side_effect = calculate_query_metrics
        tracked.summary.side_effect = summarize_query_metrics

        with (
            patch.object(evaluation.time, "perf_counter", tracked.clock),
            patch.object(evaluation, "search_keywords", tracked.search),
            patch.object(evaluation, "calculate_query_metrics", tracked.metrics),
            patch.object(evaluation, "summarize_query_metrics", tracked.summary),
        ):
            records, _ = evaluate_keyword_queries(self.documents, self.queries[:1], 3)

        self.assertEqual(
            [entry[0] for entry in tracked.mock_calls],
            ["clock", "search", "clock", "metrics", "summary"],
        )
        self.assertEqual(records[0].elapsed_seconds, 0.25)


class VectorEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.timeout = Document("a.md", "超时", "请求超时后有限重试。", "a.md")
        self.log = Document("b.md", "日志", "记录请求耗时。", "b.md")
        self.budget = Document("c.md", "预算", "检查上下文长度。", "c.md")
        self.documents = [self.log, self.budget, self.timeout]
        self.document_embeddings = {
            "b.md": [0.6, 0.8],
            "c.md": [0.0, 1.0],
            "a.md": [1.0, 0.0],
        }
        self.queries = [
            EvaluationQuery("q02", "请求超时", ["a.md", "b.md"]),
            EvaluationQuery("q01", "上下文", ["c.md"]),
            EvaluationQuery("q03", "没有资料的问题", []),
            EvaluationQuery("q04", " \t", []),
        ]
        query_vectors = {
            "query: 请求超时": [1.0, 0.0],
            "query: 上下文": [0.0, 1.0],
            "query: 没有资料的问题": [-1.0, 0.0],
        }
        self.model = Mock(spec=["encode", "get_embedding_dimension"])
        self.model.encode.side_effect = lambda text, **kwargs: np.asarray(
            query_vectors[text], dtype=np.float32
        )
        self.model.get_embedding_dimension.return_value = 2

    def test_runs_query_encoding_ranking_metrics_and_summary(self) -> None:
        with patch.object(
            evaluation.time,
            "perf_counter",
            side_effect=[10.0, 10.25, 20.0, 20.5, 30.0, 30.75, 40.0, 41.0],
        ):
            records, summary = evaluate_vector_queries(
                self.model, self.documents, self.document_embeddings, self.queries, 3
            )

        expected_results = [
            [(self.timeout, 1.0), (self.log, 0.6), (self.budget, 0.0)],
            [(self.budget, 1.0), (self.log, 0.8), (self.timeout, 0.0)],
            [(self.budget, 0.0), (self.log, -0.6), (self.timeout, -1.0)],
            [],
        ]
        expected_metrics = [
            QueryMetrics(2, 1.0, 2 / 3, 1.0),
            QueryMetrics(1, 1.0, 1 / 3, 1.0),
            QueryMetrics(0, None, 0.0, None),
            QueryMetrics(0, None, 0.0, None),
        ]
        self.assertEqual(len(records), 4)
        for record, query, results, metrics, elapsed in zip(
            records,
            self.queries,
            expected_results,
            expected_metrics,
            [0.25, 0.5, 0.75, 1.0],
            strict=True,
        ):
            with self.subTest(query_id=query.query_id):
                self.assertIsInstance(record, QueryEvaluation)
                self.assertEqual(record.query, query)
                self.assertEqual(
                    [document for document, _ in record.search_results],
                    [document for document, _ in results],
                )
                for (_, score), (_, expected_score) in zip(
                    record.search_results, results, strict=True
                ):
                    self.assertAlmostEqual(score, expected_score, delta=1e-6)
                self.assertEqual(record.metrics, metrics)
                self.assertEqual(record.elapsed_seconds, elapsed)
        self.assertEqual(summary, EvaluationSummary(2, 2, 1.0, 0.5, 1.0))
        self.assertEqual(
            self.model.encode.call_args_list,
            [
                call(f"query: {query.text}", normalize_embeddings=True)
                for query in self.queries[:3]
            ],
        )

    def test_passes_k_to_search_and_metrics_when_k_exceeds_document_count(self) -> None:
        cases = (
            (1, [self.timeout], QueryMetrics(1, 0.5, 1.0, 1.0)),
            (
                5,
                [self.timeout, self.log, self.budget],
                QueryMetrics(2, 1.0, 2 / 5, 1.0),
            ),
        )
        for k, expected_documents, expected_metrics in cases:
            with self.subTest(k=k):
                records, summary = evaluate_vector_queries(
                    self.model,
                    self.documents,
                    self.document_embeddings,
                    self.queries[:1],
                    k,
                )

                self.assertEqual(len(records), 1)
                self.assertEqual(
                    [document for document, _ in records[0].search_results],
                    expected_documents,
                )
                self.assertEqual(records[0].metrics, expected_metrics)
                self.assertEqual(
                    summary,
                    EvaluationSummary(
                        1,
                        0,
                        expected_metrics.recall,
                        expected_metrics.precision,
                        expected_metrics.rr,
                    ),
                )

    def test_empty_batch_returns_empty_records_and_summary_without_encoding(
        self,
    ) -> None:
        records, summary = evaluate_vector_queries(
            self.model, self.documents, self.document_embeddings, [], 3
        )

        self.assertEqual(records, [])
        self.assertEqual(summary, EvaluationSummary(0, 0, None, None, None))
        self.model.encode.assert_not_called()

    def test_invalid_k_raises_even_for_an_empty_batch(self) -> None:
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
        for queries in ([], self.queries):
            for k, error_type in cases:
                with (
                    self.subTest(query_count=len(queries), k=k),
                    self.assertRaises(error_type),
                ):
                    evaluate_vector_queries(
                        self.model, self.documents, self.document_embeddings, queries, k
                    )
        self.model.encode.assert_not_called()

    def test_document_embedding_id_mismatch_propagates_before_encoding(self) -> None:
        embeddings = self.document_embeddings.copy()
        del embeddings["b.md"]

        with self.assertRaisesRegex(ValueError, "Document IDs do not match"):
            evaluate_vector_queries(
                self.model, self.documents, embeddings, self.queries, 3
            )

        self.model.encode.assert_not_called()

    def test_encoding_and_metric_errors_propagate(self) -> None:
        for target, dependency in (
            (self.model, "encode"),
            (evaluation, "calculate_query_metrics"),
        ):
            error = RuntimeError(f"simulated {dependency} failure")
            with (
                self.subTest(dependency=dependency),
                patch.object(target, dependency, side_effect=error) as failing_call,
                self.assertRaises(RuntimeError) as caught,
            ):
                evaluate_vector_queries(
                    self.model,
                    self.documents,
                    self.document_embeddings,
                    self.queries,
                    3,
                )

            self.assertIs(caught.exception, error)
            failing_call.assert_called_once()

    def test_times_query_encoding_and_search_before_metrics_and_summary(self) -> None:
        tracked = Mock()
        tracked.clock.side_effect = [10.0, 10.25]
        tracked.search.side_effect = search_vectors
        tracked.metrics.side_effect = calculate_query_metrics
        tracked.summary.side_effect = summarize_query_metrics
        tracked.attach_mock(self.model.encode, "encode")

        with (
            patch.object(evaluation.time, "perf_counter", tracked.clock),
            patch.object(evaluation, "search_vectors", tracked.search),
            patch.object(evaluation, "calculate_query_metrics", tracked.metrics),
            patch.object(evaluation, "summarize_query_metrics", tracked.summary),
        ):
            records, _ = evaluate_vector_queries(
                self.model,
                self.documents,
                self.document_embeddings,
                self.queries[:1],
                3,
            )

        self.assertEqual(
            [entry[0] for entry in tracked.mock_calls],
            ["clock", "search", "encode", "clock", "metrics", "summary"],
        )
        self.assertEqual(records[0].elapsed_seconds, 0.25)


if __name__ == "__main__":
    unittest.main()

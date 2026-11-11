"""验证向量检索的查询编码、编号对应、计分与排名规则。"""

import math
import unittest
from unittest.mock import Mock, patch

import numpy as np

from rag_knowledge_base.document import Document
from rag_knowledge_base.vector_retrieval import search_vectors

ABS_TOLERANCE = 1e-6


class SearchVectorsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.timeout = Document("a.md", "超时", "请求超时后有限重试。", "a.md")
        self.log = Document("b.md", "日志", "记录请求耗时。", "b.md")
        self.budget = Document("c.md", "预算", "检查上下文长度。", "c.md")
        self.retry = Document("d.md", "重试", "设置重试上限。", "d.md")
        self.documents = [self.log, self.retry, self.timeout, self.budget]
        self.document_embeddings = {
            "c.md": [0.0, 1.0],
            "b.md": [1.0, 0.0],
            "d.md": [-1.0, 0.0],
            "a.md": [1.0, 0.0],
        }
        self.model = Mock(spec=["encode", "get_embedding_dimension"])
        self.model.encode.return_value = np.asarray([1.0, 0.0], dtype=np.float32)
        self.model.get_embedding_dimension.return_value = 2

    def test_orders_all_scores_and_ties_before_applying_k(self) -> None:
        expected = [
            (self.timeout, 1.0),
            (self.log, 1.0),
            (self.budget, 0.0),
            (self.retry, -1.0),
        ]

        for k in (1, 2, 4, 8):
            with self.subTest(k=k):
                self.model.reset_mock()

                results = search_vectors(
                    self.model,
                    self.documents,
                    self.document_embeddings,
                    "请求超时",
                    k,
                )

                expected_results = expected[:k]
                self.assertEqual(
                    [document for document, _ in results],
                    [document for document, _ in expected_results],
                )
                for (_, score), (_, expected_score) in zip(results, expected_results):
                    self.assertAlmostEqual(score, expected_score, delta=ABS_TOLERANCE)
                self.model.encode.assert_called_once_with(
                    "query: 请求超时", normalize_embeddings=True
                )
                self.model.get_embedding_dimension.assert_called_once_with()

    def test_preserves_precision_when_scores_are_close(self) -> None:
        higher_score = 0.80004
        embeddings = {
            "a.md": [0.8, 0.6],
            "b.md": [higher_score, math.sqrt(1.0 - higher_score**2)],
        }

        results = search_vectors(
            self.model, [self.timeout, self.log], embeddings, "请求超时", 2
        )

        self.assertEqual([doc for doc, _ in results], [self.log, self.timeout])
        self.assertAlmostEqual(results[0][1], higher_score, delta=ABS_TOLERANCE)
        self.assertAlmostEqual(results[1][1], 0.8, delta=ABS_TOLERANCE)

    def test_returns_empty_list_for_blank_queries_before_encoding(self) -> None:
        for query in ("", " ", "\t\n", "　"):
            with self.subTest(query=query):
                self.model.reset_mock()

                results = search_vectors(
                    self.model,
                    self.documents,
                    self.document_embeddings,
                    query,
                    4,
                )

                self.assertEqual(results, [])
                self.model.encode.assert_not_called()
                self.model.get_embedding_dimension.assert_not_called()

    def test_returns_empty_list_for_empty_corpus_before_encoding(self) -> None:
        for query in ("请求超时", ""):
            with self.subTest(query=query):
                self.model.reset_mock()

                results = search_vectors(self.model, [], {}, query, 4)

                self.assertEqual(results, [])
                self.model.encode.assert_not_called()
                self.model.get_embedding_dimension.assert_not_called()

    def test_invalid_k_raises_before_empty_input_handling(self) -> None:
        for k in (0, -1, 1.0, 1.5, True, False, "2", None):
            for query in ("请求超时", ""):
                for documents, embeddings in (
                    (self.documents, self.document_embeddings),
                    ([], {}),
                ):
                    with self.subTest(k=k, query=query, corpus_size=len(documents)):
                        self.model.reset_mock()

                        with self.assertRaisesRegex(
                            ValueError, "k must be a positive integer"
                        ):
                            search_vectors(self.model, documents, embeddings, query, k)

                        self.model.encode.assert_not_called()
                        self.model.get_embedding_dimension.assert_not_called()

    def test_rejects_missing_extra_or_replaced_document_ids_before_encoding(
        self,
    ) -> None:
        replaced = self.document_embeddings.copy()
        replaced["extra.md"] = replaced.pop("a.md")
        cases = (
            ("missing", {"a.md": [1.0, 0.0]}),
            ("extra", {**self.document_embeddings, "extra.md": [1.0, 0.0]}),
            ("replaced", replaced),
            ("empty", {}),
        )

        for name, embeddings in cases:
            with self.subTest(case=name):
                self.model.reset_mock()

                with self.assertRaisesRegex(ValueError, "Document IDs"):
                    search_vectors(
                        self.model, self.documents, embeddings, "请求超时", 4
                    )

                self.model.encode.assert_not_called()
                self.model.get_embedding_dimension.assert_not_called()

    def test_query_validation_failure_stops_scoring(self) -> None:
        cases = (
            ([0.0, 0.0], "zero"),
            ([1.0, np.nan], "finite"),
            ([1.0, 0.0, 0.0], "dimension"),
        )

        for values, reason in cases:
            with self.subTest(values=values, reason=reason):
                self.model.reset_mock()
                self.model.encode.return_value = np.asarray(values)

                with patch(
                    "rag_knowledge_base.vector_retrieval.cosine_similarity_unchecked"
                ) as scorer:
                    with self.assertRaisesRegex(ValueError, reason):
                        search_vectors(
                            self.model,
                            self.documents,
                            self.document_embeddings,
                            "请求超时",
                            4,
                        )

                    scorer.assert_not_called()
                self.model.encode.assert_called_once_with(
                    "query: 请求超时", normalize_embeddings=True
                )


if __name__ == "__main__":
    unittest.main()

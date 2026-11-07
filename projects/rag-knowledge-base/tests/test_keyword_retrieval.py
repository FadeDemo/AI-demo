"""验证关键词检索的词项切分、计分与排名规则。"""

import unittest

from rag_knowledge_base.document import Document
from rag_knowledge_base.keyword_retrieval import (
    score_document,
    search_keywords,
    tokenize,
)


class TokenizeTests(unittest.TestCase):
    def test_chinese_bigrams_overlap_without_a_trailing_single_character(self) -> None:
        cases = (
            ("超时", {"超时"}),
            ("请求超", {"请求", "求超"}),
            ("请求超时", {"请求", "求超", "超时"}),
            ("请求超时后", {"请求", "求超", "超时", "时后"}),
        )

        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(tokenize(text), expected)

    def test_preserves_single_character_chinese_fragments(self) -> None:
        cases = (
            ("超", {"超"}),
            ("超，时", {"超", "时"}),
            ("超 超时", {"超", "超时"}),
        )

        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(tokenize(text), expected)

    def test_normalizes_ascii_words_numbers_and_underscores(self) -> None:
        self.assertEqual(
            tokenize("REQUEST_TIMEOUT HTTP_429 500 _tmp python3 abc123 123abc"),
            {
                "request_timeout",
                "http_429",
                "500",
                "_tmp",
                "python3",
                "abc123",
                "123abc",
            },
        )

    def test_deduplicates_repeated_chinese_and_ascii_terms(self) -> None:
        self.assertEqual(
            tokenize("请求请求 请求请求 HTTP http HTTP"),
            {"请求", "求请", "http"},
        )

    def test_punctuation_and_whitespace_separate_fragments(self) -> None:
        for separator in (" ", "\t", "\n", ",", "，", "。", "-", "/", "#"):
            with self.subTest(separator=separator):
                self.assertEqual(tokenize(f"请求{separator}超时"), {"请求", "超时"})
                self.assertEqual(
                    tokenize(f"REQUEST{separator}TIMEOUT"), {"request", "timeout"}
                )

    def test_handles_adjacent_chinese_and_ascii_fragments(self) -> None:
        cases = (
            ("请求HTTP_429超时", {"请求", "http_429", "超时"}),
            ("超HTTP时", {"超", "http", "时"}),
        )

        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(tokenize(text), expected)

    def test_returns_empty_set_for_empty_text_or_only_separators(self) -> None:
        for text in ("", " ", "\t\n", "，。！？", "#-()/"):
            with self.subTest(text=text):
                self.assertEqual(tokenize(text), set())


class ScoreDocumentTests(unittest.TestCase):
    def test_scores_course_documents(self) -> None:
        query_terms = {"请求", "求超", "超时"}
        cases = (
            ("超时", "请求超时后有限重试。", 3),
            ("日志", "记录请求耗时与超时类别。", 2),
            ("预算", "发送前检查上下文长度。", 0),
        )

        for title, text, expected in cases:
            with self.subTest(title=title):
                document = Document(f"{title}.md", title, text, f"{title}.md")

                self.assertEqual(score_document(query_terms, document), expected)

    def test_counts_matches_in_both_title_and_body(self) -> None:
        document = Document("a.md", "超时", "记录请求。", "a.md")

        self.assertEqual(score_document({"超时", "请求"}, document), 2)

    def test_repeated_terms_count_once_across_title_and_body(self) -> None:
        cases = (
            ({"请求", "求超", "超时"}, "超时", "请求超时，请求超时。", 3),
            (
                {"request_timeout"},
                "REQUEST_TIMEOUT",
                "request_timeout REQUEST_TIMEOUT",
                1,
            ),
        )

        for query_terms, title, text, expected in cases:
            with self.subTest(title=title):
                document = Document("a.md", title, text, "a.md")

                self.assertEqual(score_document(query_terms, document), expected)

    def test_title_and_body_do_not_form_a_cross_boundary_term(self) -> None:
        cases = (
            ({"请求"}, "请", "求"),
            ({"requesttimeout"}, "request", "timeout"),
        )

        for query_terms, title, text in cases:
            with self.subTest(title=title):
                document = Document("a.md", title, text, "a.md")

                self.assertEqual(score_document(query_terms, document), 0)

    def test_empty_or_unmatched_query_terms_score_zero(self) -> None:
        document = Document("a.md", "超时", "请求超时。", "a.md")

        for query_terms in (set(), {"火山"}):
            with self.subTest(query_terms=query_terms):
                self.assertEqual(score_document(query_terms, document), 0)

    def test_document_id_and_source_do_not_contribute_to_score(self) -> None:
        document = Document(
            "requests/超时.md", "预算", "检查上下文长度。", "request_timeout.md"
        )

        self.assertEqual(score_document({"超时", "request_timeout"}, document), 0)


class SearchKeywordsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.budget = Document("预算.md", "预算", "发送前检查上下文长度。", "预算.md")
        self.log = Document("日志.md", "日志", "记录请求耗时与超时类别。", "日志.md")
        self.timeout = Document("超时.md", "超时", "请求超时后有限重试。", "超时.md")
        self.documents = [self.budget, self.log, self.timeout]

    def test_returns_course_ranking_and_excludes_zero_scores(self) -> None:
        for query in ("请求超时", "请求超时 请求超时"):
            with self.subTest(query=query):
                self.assertEqual(
                    search_keywords(self.documents, query, 5),
                    [(self.timeout, 3), (self.log, 2)],
                )

    def test_limits_results_after_sorting_by_score(self) -> None:
        self.assertEqual(
            search_keywords(self.documents, "请求超时", 1),
            [(self.timeout, 3)],
        )

    def test_breaks_score_ties_by_document_id_before_limiting_results(self) -> None:
        first = Document("a.md", "超时", "", "a.md")
        second = Document("b.md", "超时", "", "b.md")

        for documents in ([second, first], [first, second]):
            for k, expected in ((1, [(first, 1)]), (2, [(first, 1), (second, 1)])):
                with self.subTest(doc_ids=[doc.doc_id for doc in documents], k=k):
                    self.assertEqual(
                        search_keywords(documents, "超时", k),
                        expected,
                    )

    def test_returns_empty_list_for_empty_or_unmatched_queries(self) -> None:
        for query in ("", " \t\n", "，！？", "火山"):
            with self.subTest(query=query):
                self.assertEqual(search_keywords(self.documents, query, 5), [])

    def test_returns_empty_list_for_an_empty_corpus(self) -> None:
        for query in ("请求超时", ""):
            with self.subTest(query=query):
                self.assertEqual(search_keywords([], query, 5), [])

    def test_invalid_k_raises_even_with_an_empty_query_or_corpus(self) -> None:
        for k in (0, -1, 1.0, 1.5, True, False, "2", None):
            for query in ("请求超时", ""):
                for documents in (self.documents, []):
                    with (
                        self.subTest(k=k, query=query, corpus_size=len(documents)),
                        self.assertRaises(ValueError),
                    ):
                        search_keywords(documents, query, k)


if __name__ == "__main__":
    unittest.main()

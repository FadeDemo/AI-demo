import logging

import pytest

from engineering_foundations.search import Document, search_documents


@pytest.fixture
def sample_documents() -> list[Document]:
    return [
        Document(title="RAG Guide", content="retrieval augmented", source="rag.md"),
        Document(title="Logging", content="observable events", source="logging.md"),
        Document(title="Another RAG", content="more RAG examples", source="more.md"),
    ]


@pytest.mark.parametrize("query", ["RAG", "rag", " Rag "])
def test_search_normalizes_query(sample_documents: list[Document], query: str) -> None:
    results = search_documents(sample_documents, query, request_id="req-test")

    assert [result.document.source for result in results] == ["more.md", "rag.md"]


def test_search_respects_limit(sample_documents: list[Document]) -> None:
    results = search_documents(sample_documents, "rag", request_id="req-test", limit=1)

    assert len(results) == 1
    assert results[0].document.source == "more.md"


@pytest.mark.parametrize("limit", [0, -1])
def test_invalid_limit_is_rejected(
    sample_documents: list[Document], limit: int
) -> None:
    with pytest.raises(ValueError, match="limit must be at least 1"):
        search_documents(
            sample_documents, "rag", request_id="req-invalid-limit", limit=limit
        )


def test_empty_query_is_rejected_with_context(
    sample_documents: list[Document], caplog: pytest.LogCaptureFixture
) -> None:
    with (
        caplog.at_level(logging.WARNING, logger="engineering_foundations.search"),
        pytest.raises(ValueError, match="query must not be empty"),
    ):
        search_documents(sample_documents, " ", request_id="req-empty")

    record = caplog.records[-1]
    assert record.levelno == logging.WARNING
    assert record.event == "search_rejected"
    assert record.request_id == "req-empty"
    assert record.reason == "empty_query"


def test_success_logs_share_request_id(
    sample_documents: list[Document], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="engineering_foundations.search"):
        search_documents(sample_documents, "logging", request_id="req-success")

    records = [record for record in caplog.records if record.levelno == logging.INFO]
    assert [record.event for record in records] == [
        "search_started",
        "search_completed",
    ]
    assert {record.request_id for record in records} == {"req-success"}
    assert records[-1].result_count == 1


def test_no_results_logs_safe_context(
    sample_documents: list[Document], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="engineering_foundations.search"):
        results = search_documents(
            sample_documents, "no-such-document", request_id="req-no-results"
        )
    assert len(results) == 0
    found_search_completed = False
    found_search_no_results = False
    for record in caplog.records:
        if record.event == "search_no_results":
            found_search_no_results = True
            assert record.levelno == logging.INFO
            assert record.request_id == "req-no-results"
            assert record.query_length == len("no-such-document".strip().casefold())
            assert not hasattr(record, "query")
        elif record.event == "search_completed":
            found_search_completed = True
            assert record.result_count == 0
            assert record.request_id == "req-no-results"

    assert found_search_no_results, "search_no_results log not found"
    assert found_search_completed, "search_completed log not found"

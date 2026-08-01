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

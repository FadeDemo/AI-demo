import logging
from dataclasses import dataclass
from time import perf_counter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Document:
    title: str
    content: str
    source: str


@dataclass(frozen=True)
class SearchResult:
    document: Document
    score: int


def search_documents(
    documents: list[Document],
    query: str,
    *,
    request_id: str,
    limit: int = 3,
) -> list[SearchResult]:
    """Return case-insensitive substring matches ordered by a simple score."""
    normalized_query = query.strip().casefold()
    if not normalized_query:
        logger.warning(
            "empty search query rejected",
            extra={
                "event": "search_rejected",
                "request_id": request_id,
                "reason": "empty_query",
            },
        )
        raise ValueError("query must not be empty")
    if limit < 1:
        logger.warning(
            "invalid result limit rejected",
            extra={
                "event": "search_rejected",
                "request_id": request_id,
                "reason": "invalid_limit",
            },
        )
        raise ValueError("limit must be at least 1")

    started_at = perf_counter()
    logger.info(
        "search started",
        extra={
            "event": "search_started",
            "request_id": request_id,
            "document_count": len(documents),
            "query_length": len(normalized_query),
        },
    )

    results = []
    for document in documents:
        title = document.title.casefold()
        content = document.content.casefold()
        score = title.count(normalized_query) * 2 + content.count(normalized_query)
        if score:
            results.append(SearchResult(document=document, score=score))

    results.sort(key=lambda result: (-result.score, result.document.source))
    selected_results = results[:limit]
    logger.info(
        "search completed",
        extra={
            "event": "search_completed",
            "request_id": request_id,
            "result_count": len(selected_results),
            "duration_ms": round((perf_counter() - started_at) * 1000, 3),
        },
    )
    return selected_results

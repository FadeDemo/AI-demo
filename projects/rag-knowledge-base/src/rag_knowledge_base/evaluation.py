import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from rag_knowledge_base.document import Document
from rag_knowledge_base.keyword_retrieval import search_keywords


@dataclass
class EvaluationQuery:
    query_id: str
    text: str
    relevant_doc_ids: list[str]


def load_evaluation_queries(
    queries_path: Path,
    documents: list[Document],
) -> list[EvaluationQuery]:
    if not queries_path.exists():
        raise FileNotFoundError(f"Queries file not found: {queries_path}")
    if queries_path.is_dir():
        raise ValueError(f"Queries path is a directory: {queries_path}")
    if queries_path.suffix.lower() != ".json":
        raise ValueError(f"Queries file must be a JSON file: {queries_path}")
    with open(queries_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        counter = Counter([query["query_id"] for query in data])
        doc_ids = {doc.doc_id for doc in documents}
        results = []
        for query in data:
            if counter[query["query_id"]] > 1:
                raise ValueError(f"Duplicate query ID: {query['query_id']}")
            if query.get("relevant_doc_ids", None) is None:
                raise ValueError(
                    f"Relevant document IDs are required for query: {query['query_id']}"
                )
            relevant_counter = Counter(query["relevant_doc_ids"])
            for relative_doc_id in query["relevant_doc_ids"]:
                if relevant_counter[relative_doc_id] > 1:
                    raise ValueError(
                        f"Duplicate relevant document ID: {relative_doc_id}"
                    )
                if relative_doc_id not in doc_ids:
                    raise ValueError(
                        f"Relative document ID not found: {relative_doc_id}"
                    )
            results.append(
                EvaluationQuery(
                    query_id=query["query_id"],
                    text=query["text"],
                    relevant_doc_ids=query["relevant_doc_ids"],
                )
            )
        return results


@dataclass
class QueryMetrics:
    hit_count: int
    recall: float | None
    precision: float
    rr: float | None


def calculate_query_metrics(
    query: EvaluationQuery,
    ranked_doc_ids: list[str],
    k: int,
    valid_doc_ids: set[str],
) -> QueryMetrics:
    if not isinstance(k, int) or isinstance(k, bool):
        raise TypeError(f"K must be an integer: {k}")
    if k <= 0:
        raise ValueError(f"K must be greater than 0: {k}")
    counter = Counter(ranked_doc_ids)
    for ranked_doc_id in ranked_doc_ids:
        if counter[ranked_doc_id] > 1:
            raise ValueError(f"Duplicate ranked document ID: {ranked_doc_id}")
        if ranked_doc_id not in valid_doc_ids:
            raise ValueError(f"Ranked document ID not found: {ranked_doc_id}")
    hit_count = 0
    rr = None
    for i, ranked_doc_id in enumerate(ranked_doc_ids[:k]):
        if ranked_doc_id in query.relevant_doc_ids:
            hit_count += 1
            if rr is None:
                rr = 1 / (i + 1)
    recall = (
        hit_count / len(query.relevant_doc_ids)
        if len(query.relevant_doc_ids) > 0
        else None
    )
    precision = hit_count / k
    if len(query.relevant_doc_ids) > 0 and rr is None:
        rr = 0.0
    return QueryMetrics(
        hit_count=hit_count,
        recall=recall,
        precision=precision,
        rr=rr,
    )


@dataclass
class EvaluationSummary:
    answerable_count: int
    unanswerable_count: int
    mean_recall: float | None
    mean_precision: float | None
    mrr: float | None


def summarize_query_metrics(
    metrics: list[QueryMetrics],
) -> EvaluationSummary:
    unanswerable_count = 0
    mean_recall = None
    mean_precision = 0.0
    mrr = None
    for metric in metrics:
        if metric.recall is None:
            unanswerable_count += 1
        else:
            if mean_recall is None:
                mean_recall = 0.0
            if mrr is None:
                mrr = 0.0
            mean_recall += metric.recall
            mean_precision += metric.precision
            mrr += metric.rr
    mean_recall = (
        mean_recall / (len(metrics) - unanswerable_count)
        if mean_recall is not None and len(metrics) != unanswerable_count
        else None
    )
    mean_precision = (
        mean_precision / (len(metrics) - unanswerable_count)
        if len(metrics) != unanswerable_count
        else None
    )
    mrr = (
        mrr / (len(metrics) - unanswerable_count)
        if mrr is not None and len(metrics) != unanswerable_count
        else None
    )
    return EvaluationSummary(
        answerable_count=len(metrics) - unanswerable_count,
        unanswerable_count=unanswerable_count,
        mean_recall=mean_recall,
        mean_precision=mean_precision,
        mrr=mrr,
    )


@dataclass
class QueryEvaluation:
    query: EvaluationQuery
    search_results: list[tuple[Document, float]]
    metrics: QueryMetrics
    elapsed_seconds: float


def evaluate_keyword_queries(
    documents: list[Document],
    queries: list[EvaluationQuery],
    k: int,
) -> tuple[list[QueryEvaluation], EvaluationSummary]:
    if not isinstance(k, int) or isinstance(k, bool):
        raise TypeError(f"K must be an integer: {k}")
    if k <= 0:
        raise ValueError(f"K must be greater than 0: {k}")
    query_evaluations = []
    query_metrics = []
    for query in queries:
        start = time.perf_counter()
        results: list[tuple[Document, int]] = search_keywords(documents, query.text, k)
        end = time.perf_counter()
        metrics = calculate_query_metrics(
            query,
            [document.doc_id for document, _ in results],
            k,
            {document.doc_id for document in documents},
        )
        query_evaluations.append(
            QueryEvaluation(
                query=query,
                search_results=results,
                metrics=metrics,
                elapsed_seconds=end - start,
            )
        )
        query_metrics.append(metrics)
    evaluation_summary = summarize_query_metrics(query_metrics)
    return query_evaluations, evaluation_summary

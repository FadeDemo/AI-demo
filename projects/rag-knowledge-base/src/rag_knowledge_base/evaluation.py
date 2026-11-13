import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from rag_knowledge_base.document import Document


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

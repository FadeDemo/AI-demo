import re

from rag_knowledge_base.document import Document


def tokenize(text: str) -> set[str]:
    fragments = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", text.lower())
    result = set[str]()
    for fragment in fragments:
        if fragment[0] >= "\u4e00" and fragment[0] <= "\u9fff":
            length = len(fragment)
            if length > 1:
                result.update([fragment[i : i + 2] for i in range(length - 1)])
            else:
                result.add(fragment)
        else:
            result.add(fragment)
    return result


def score_document(query_terms: set[str], document: Document) -> int:
    text = document.title + "\n" + document.text
    text_terms = tokenize(text)
    return len(query_terms & text_terms)


def search_keywords(
    documents: list[Document], query: str, k: int
) -> list[tuple[Document, int]]:
    if not type(k) == int or k <= 0:
        raise ValueError("k must be a positive integer")
    query_terms = tokenize(query)
    results = []
    for document in documents:
        score = score_document(query_terms, document)
        if score > 0:
            results.append((document, score))
    results.sort(key=lambda x: (-x[1], x[0].doc_id))
    return results[:k]

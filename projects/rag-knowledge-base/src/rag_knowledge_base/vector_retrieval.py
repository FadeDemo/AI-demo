from sentence_transformers import SentenceTransformer

from rag_knowledge_base.document import Document
from rag_knowledge_base.embedding import encode_query
from rag_knowledge_base.similarity import cosine_similarity_unchecked


def search_vectors(
    model: SentenceTransformer,
    documents: list[Document],
    document_embeddings: dict[str, list[float]],
    query: str,
    k: int,
) -> list[tuple[Document, float]]:
    if not type(k) == int or k <= 0:
        raise ValueError("k must be a positive integer")
    results = []
    if not query.strip() or not documents:
        return results
    if {doc.doc_id for doc in documents} != set(document_embeddings):
        raise ValueError("Document IDs do not match")
    query_embedding = encode_query(model, query)
    for doc_id, embedding in document_embeddings.items():
        similarity = cosine_similarity_unchecked(query_embedding, embedding)
        results.append(
            (next(doc for doc in documents if doc.doc_id == doc_id), similarity)
        )
    results.sort(key=lambda x: (-x[1], x[0].doc_id))
    return results[:k]

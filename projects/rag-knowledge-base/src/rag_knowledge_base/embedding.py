from sentence_transformers import SentenceTransformer

from rag_knowledge_base.chunking import Chunk
from rag_knowledge_base.document import Document
from rag_knowledge_base.similarity import validate_vector


def encode_query(model: SentenceTransformer, query: str) -> list[float]:
    prompt = f"query: {query}"
    embedding = model.encode(prompt, normalize_embeddings=True).tolist()
    validate_embedding(embedding, model)
    return embedding


def encode_document(model: SentenceTransformer, document: Document) -> list[float]:
    input_text = f"passage: {document.title}\n{document.text}"
    return _encode_passage(model, input_text, f"Document {document.doc_id}")


def validate_embedding(embedding: list[float], model: SentenceTransformer) -> None:
    validate_vector(embedding)
    expected_dimension = model.get_embedding_dimension()
    if len(embedding) != expected_dimension:
        raise ValueError(
            f"Embedding dimension mismatch: {len(embedding)} != {expected_dimension}"
        )


def encode_documents(
    model: SentenceTransformer,
    documents: list[Document],
) -> dict[str, list[float]]:
    return {document.doc_id: encode_document(model, document) for document in documents}


def _encode_passage(
    model: SentenceTransformer, input_text: str, label: str
) -> list[float]:
    input_ids = model.tokenizer(input_text, truncation=False)["input_ids"]
    if len(input_ids) > model.max_seq_length:
        raise ValueError(
            f"{label} is too long: {len(input_ids)} > {model.max_seq_length}"
        )
    embedding = model.encode(input_text, normalize_embeddings=True).tolist()
    validate_embedding(embedding, model)
    return embedding


def encode_chunk(model: SentenceTransformer, chunk: Chunk) -> list[float]:
    input_text = f"passage: {chunk.title}\n{chunk.text}"
    return _encode_passage(model, input_text, f"Chunk {chunk.chunk_id}")


def encode_chunks(
    model: SentenceTransformer, chunks: list[Chunk]
) -> dict[str, list[float]]:
    return {chunk.chunk_id: encode_chunk(model, chunk) for chunk in chunks}

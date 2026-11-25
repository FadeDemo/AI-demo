from rag_knowledge_base.chunking import Chunk


def build_evidence_map(chunks: list[Chunk]) -> dict[str, Chunk]:
    return {f"E{i}": chunk for i, chunk in enumerate(chunks, start=1)}

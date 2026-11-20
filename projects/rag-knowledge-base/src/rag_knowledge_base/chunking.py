from typing import Any


def split_text(text: str, chunk_size: int, overlap: int) -> list[tuple[int, int, str]]:
    def check_int(value: Any) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"Expected an integer, got {type(value)}")
        if value < 0:
            raise ValueError(f"Expected a non-negative integer, got {value}")

    check_int(chunk_size)
    if chunk_size == 0:
        raise ValueError("Chunk size must be positive")
    check_int(overlap)
    if overlap >= chunk_size:
        raise ValueError(
            f"Overlap must be less than chunk size, got {overlap} >= {chunk_size}"
        )
    if not text:
        return []
    result = []
    for i in range(0, len(text), chunk_size - overlap):
        start = i
        end = min(i + chunk_size, len(text))
        chunk = text[start:end]
        result.append((start, end, chunk))
        if end == len(text):
            break
    return result

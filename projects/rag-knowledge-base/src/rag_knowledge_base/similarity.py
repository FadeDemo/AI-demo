import math
from collections.abc import Sequence

import numpy as np


def cosine_similarity_unchecked(a, b) -> float:
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def cosine_similarity(a: Sequence[int | float], b: Sequence[int | float]) -> float:
    validate_vector(a)
    validate_vector(b)
    if len(a) != len(b):
        raise ValueError("Vectors must have the same length")
    return cosine_similarity_unchecked(a, b)


def validate_vector(vector: Sequence[int | float]) -> None:
    if not vector:
        raise ValueError("Vector cannot be empty")
    if any(not isinstance(x, (int, float)) or isinstance(x, bool) for x in vector):
        raise ValueError("Vector must contain only numbers")
    if any(not math.isfinite(x) for x in vector):
        raise ValueError("Vector must contain only finite numbers")
    if not np.any(vector):
        raise ValueError("Vector cannot be zero vector")

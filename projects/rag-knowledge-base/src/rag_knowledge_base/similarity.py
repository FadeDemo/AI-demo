import math
from collections.abc import Sequence

import numpy as np


def cosine_similarity(a: Sequence[int | float], b: Sequence[int | float]) -> float:
    if not a or not b:
        raise ValueError("Vectors cannot be empty")
    if len(a) != len(b):
        raise ValueError("Vectors must have the same length")
    if any(not isinstance(x, (int, float)) or isinstance(x, bool) for x in a) or any(
        not isinstance(x, (int, float)) or isinstance(x, bool) for x in b
    ):
        raise ValueError("Vectors must contain only numbers")
    if any(not math.isfinite(x) or not math.isfinite(y) for (x, y) in zip(a, b)):
        raise ValueError("Vectors must contain only finite numbers")
    if not np.any(a) or not np.any(b):
        raise ValueError("Vectors cannot be zero vectors")
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

"""验证余弦相似度的计算结果和非法输入拒绝。"""

import math
import unittest

from rag_knowledge_base.similarity import cosine_similarity

ABS_TOLERANCE = 1e-6


class CosineSimilarityTests(unittest.TestCase):
    def test_same_perpendicular_and_opposite_directions(self) -> None:
        for other, expected in (([1, 0], 1.0), ([0, 1], 0.0), ([-1, 0], -1.0)):
            with self.subTest(other=other):
                self.assertAlmostEqual(
                    cosine_similarity([1, 0], other),
                    expected,
                    delta=ABS_TOLERANCE,
                )

    def test_positive_scaling_preserves_similarity(self) -> None:
        for a, b in (
            ([3, 4], [1, 0]),
            ([6, 8], [1, 0]),
            ([3, 4], [2, 0]),
        ):
            with self.subTest(a=a, b=b):
                self.assertAlmostEqual(
                    cosine_similarity(a, b), 0.6, delta=ABS_TOLERANCE
                )

    def test_course_document_scores_retain_calculation_precision(self) -> None:
        for document, expected in (([0.8, 0.6], 0.8), ([2, 2], 1 / math.sqrt(2))):
            with self.subTest(document=document):
                self.assertAlmostEqual(
                    cosine_similarity([1, 0], document),
                    expected,
                    delta=ABS_TOLERANCE,
                )

    def test_supports_one_and_three_dimensions(self) -> None:
        for a, b, expected in (
            ([-2], [3], -1.0),
            ([1, 2, 2], [1, 0, 0], 1 / 3),
        ):
            with self.subTest(a=a, b=b):
                self.assertAlmostEqual(
                    cosine_similarity(a, b), expected, delta=ABS_TOLERANCE
                )

    def test_accepts_small_nonzero_vectors(self) -> None:
        for a, b in (
            ([1e-9, 0], [1, 0]),
            ([1, 0], [1e-9, 0]),
            ([1e-9, 0], [1e-9, 0]),
        ):
            with self.subTest(a=a, b=b):
                self.assertAlmostEqual(
                    cosine_similarity(a, b), 1.0, delta=ABS_TOLERANCE
                )

    def test_rejects_empty_vectors(self) -> None:
        for a, b in (([], []), ([], [1, 0]), ([1, 0], [])):
            with self.subTest(a=a, b=b), self.assertRaises(ValueError):
                cosine_similarity(a, b)

    def test_rejects_dimension_mismatch(self) -> None:
        for a, b in (([1], [1, 0]), ([1, 0], [1])):
            with self.subTest(a=a, b=b), self.assertRaises(ValueError):
                cosine_similarity(a, b)

    def test_rejects_zero_vectors_on_either_side(self) -> None:
        for a, b in (
            ([0, 0], [1, 0]),
            ([1, 0], [0, 0]),
            ([0, 0], [0, 0]),
        ):
            with self.subTest(a=a, b=b), self.assertRaises(ValueError):
                cosine_similarity(a, b)

    def test_rejects_nonnumeric_components_on_either_side(self) -> None:
        for value in ("3", None):
            for a, b in (([value, 0], [1, 0]), ([1, 0], [value, 0])):
                with self.subTest(a=a, b=b), self.assertRaises(ValueError):
                    cosine_similarity(a, b)

    def test_rejects_nonfinite_components_on_either_side(self) -> None:
        for value in (math.nan, math.inf, -math.inf):
            for a, b in (([1, value], [1, 0]), ([1, 0], [1, value])):
                with self.subTest(a=a, b=b), self.assertRaises(ValueError):
                    cosine_similarity(a, b)


if __name__ == "__main__":
    unittest.main()

"""验证固定长度切分的片段区间与边界。"""

import unittest

from rag_knowledge_base.chunking import split_text


class SplitTextTests(unittest.TestCase):
    def test_course_example_stops_after_covering_the_end(self) -> None:
        self.assertEqual(
            split_text("ABCDEFGHIJKLMN", 6, 2),
            [(0, 6, "ABCDEF"), (4, 10, "EFGHIJ"), (8, 14, "IJKLMN")],
        )

    def test_short_tail_ends_at_the_text_length(self) -> None:
        cases = (
            (0, [(0, 6, "ABCDEF"), (6, 7, "G")]),
            (2, [(0, 6, "ABCDEF"), (4, 7, "EFG")]),
        )
        for overlap, expected in cases:
            with self.subTest(overlap=overlap):
                self.assertEqual(split_text("ABCDEFG", 6, overlap), expected)

    def test_overlap_one_less_than_chunk_size(self) -> None:
        self.assertEqual(
            split_text("ABCDE", 4, 3),
            [(0, 4, "ABCD"), (1, 5, "BCDE")],
        )

    def test_empty_or_single_chunk_text(self) -> None:
        cases = (
            ("", []),
            ("ABCDE", [(0, 5, "ABCDE")]),
            ("ABCDEF", [(0, 6, "ABCDEF")]),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(split_text(text, 6, 2), expected)

    def test_offsets_count_code_points_and_keep_whitespace(self) -> None:
        self.assertEqual(
            split_text("甲🙂 乙丙", 3, 1),
            [(0, 3, "甲🙂 "), (2, 5, " 乙丙")],
        )

    def test_rejects_invalid_parameters_even_for_empty_text(self) -> None:
        cases = (
            (0, 0, ValueError),
            (-1, 0, ValueError),
            (6, -1, ValueError),
            (6, 6, ValueError),
            (6, 7, ValueError),
            (6.0, 0, TypeError),
            (6, 0.5, TypeError),
            (6, False, TypeError),
        )
        for chunk_size, overlap, error in cases:
            with self.subTest(chunk_size=chunk_size, overlap=overlap):
                with self.assertRaises(error):
                    split_text("", chunk_size, overlap)

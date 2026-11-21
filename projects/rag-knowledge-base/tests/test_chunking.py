"""验证固定长度切分和文档片段记录。"""

import unittest
from dataclasses import replace

from rag_knowledge_base.chunking import Chunk, chunk_document, split_text
from rag_knowledge_base.document import Document


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


class ChunkDocumentTests(unittest.TestCase):
    def test_returns_exact_slices_with_document_metadata(self) -> None:
        document = Document(
            doc_id="guide.md",
            title="指南",
            text="ABCD EFG",
            source="docs/guide.md",
        )

        chunks = chunk_document(document, "v1", 6, 2)

        self.assertEqual(
            [(chunk.start, chunk.end, chunk.text) for chunk in chunks],
            [(0, 6, "ABCD E"), (4, 8, " EFG")],
        )
        self.assertEqual(len({chunk.chunk_id for chunk in chunks}), len(chunks))
        for chunk in chunks:
            with self.subTest(start=chunk.start):
                self.assertIsInstance(chunk, Chunk)
                self.assertEqual(chunk.doc_id, document.doc_id)
                self.assertEqual(chunk.document_version, "v1")
                self.assertEqual(chunk.title, document.title)
                self.assertEqual(chunk.source, document.source)
                self.assertIsNone(chunk.section)

    def test_chunk_id_is_stable_and_distinguishes_inputs(self) -> None:
        document = Document("guide.md", "指南", "ABCD", "docs/guide.md")
        base_id = chunk_document(document, "v1", 6, 2)[0].chunk_id
        cases = (
            ("doc_id", replace(document, doc_id="other/guide.md"), "v1", 6, 2),
            ("version", document, "v2", 6, 2),
            ("chunk_size", document, "v1", 7, 2),
            ("overlap", document, "v1", 6, 1),
        )
        for changed, current_document, version, chunk_size, overlap in cases:
            with self.subTest(changed=changed):
                chunks = chunk_document(current_document, version, chunk_size, overlap)
                self.assertNotEqual(chunks[0].chunk_id, base_id)

        self.assertEqual(chunk_document(document, "v1", 6, 2)[0].chunk_id, base_id)

    def test_empty_document_still_checks_chunking_parameters(self) -> None:
        document = Document("empty.md", "空文档", "", "docs/empty.md")

        self.assertEqual(chunk_document(document, "v1", 6, 2), [])
        with self.assertRaisesRegex(ValueError, "Overlap must be less than chunk size"):
            chunk_document(document, "v1", 6, 6)

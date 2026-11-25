"""验证证据编号到已选片段的映射。"""

import unittest

from rag_knowledge_base.chunking import prepare_chunks
from rag_knowledge_base.document import Document
from rag_knowledge_base.evidence import build_evidence_map


class EvidenceMapTests(unittest.TestCase):
    def test_preserves_selected_order_and_source(self) -> None:
        documents = [
            Document("D1", "重试", "最多三次。认证即停。", "docs/D1"),
            Document("D2", "日志", "保留类别。", "docs/D2"),
        ]
        chunks = prepare_chunks(documents, "v1", 5, 0)
        selected = [chunks[1], chunks[2], chunks[0]]

        evidence = build_evidence_map(selected)

        self.assertEqual(list(evidence), ["E1", "E2", "E3"])
        self.assertIs(evidence["E1"], chunks[1])
        self.assertIs(evidence["E2"], chunks[2])
        self.assertIs(evidence["E3"], chunks[0])
        self.assertEqual(evidence["E1"].doc_id, "D1")
        self.assertEqual(evidence["E1"].document_version, "v1")
        self.assertEqual(evidence["E1"].source, "docs/D1")
        self.assertEqual((evidence["E1"].start, evidence["E1"].end), (5, 10))
        self.assertEqual(evidence["E1"].text, "认证即停。")

    def test_empty_input_returns_empty_mapping(self) -> None:
        self.assertEqual(build_evidence_map([]), {})

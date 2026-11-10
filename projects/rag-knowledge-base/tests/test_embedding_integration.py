"""显式启用后，用固定版本的真实模型验收两侧编码。"""

import json
import os
import platform
import unittest
from importlib.metadata import version
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from rag_knowledge_base.document_loader import load_document, load_documents
from rag_knowledge_base.embedding import encode_documents, encode_query

MODEL_ID = "intfloat/multilingual-e5-small"
MODEL_REVISION = "fd1525a9fd15316a2d503bf26ab031a61d056e98"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_CACHE = PROJECT_ROOT.parent.parent / ".cache" / "huggingface"
DOCUMENT_IDS = ("超时.md", "日志.md", "预算.md")
QUERIES = (
    "请求一直没有返回怎么办？",
    "怎样记录请求耗时？",
    "发送前怎样检查上下文长度？",
)


@unittest.skipUnless(
    os.environ.get("RAG_RUN_REAL_EMBEDDING_TESTS") == "1",
    "Set RAG_RUN_REAL_EMBEDDING_TESTS=1 to run the real-model integration test",
)
class RealEmbeddingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = SentenceTransformer(
            MODEL_ID,
            revision=MODEL_REVISION,
            cache_folder=str(MODEL_CACHE),
            device="cpu",
            token=False,
        )

    def test_encodes_fixed_inputs_then_prepares_full_corpus(self) -> None:
        corpus_root = PROJECT_ROOT / "data" / "docs"
        documents = []
        for doc_id in DOCUMENT_IDS:
            document = load_document(corpus_root / doc_id, corpus_root)
            self.assertIsNotNone(document, f"Fixture document is empty: {doc_id}")
            documents.append(document)

        document_embeddings = encode_documents(self.model, documents)
        self.assertEqual(set(document_embeddings), set(DOCUMENT_IDS))
        dimension = self.model.get_embedding_dimension()
        self.assertEqual(dimension, 384)

        encoded_inputs = [
            ("document", doc_id, document_embeddings[doc_id]) for doc_id in DOCUMENT_IDS
        ]
        for query in QUERIES:
            encoded_inputs.append(("query", query, encode_query(self.model, query)))

        results = []
        for kind, label, embedding in encoded_inputs:
            self.assertEqual(len(embedding), dimension, msg=label)
            norm = float(np.linalg.norm(embedding))
            self.assertAlmostEqual(norm, 1.0, delta=1e-5, msg=label)
            results.append(
                {
                    "kind": kind,
                    "input": label,
                    "dimension": len(embedding),
                    "norm": norm,
                }
            )

        all_documents = load_documents(corpus_root)
        all_embeddings = encode_documents(self.model, all_documents)
        self.assertEqual(len(all_embeddings), len(all_documents))
        self.assertEqual(set(all_embeddings), {doc.doc_id for doc in all_documents})
        for doc_id, embedding in all_embeddings.items():
            self.assertEqual(len(embedding), dimension, msg=doc_id)

        report = {
            "model": MODEL_ID,
            "revision": MODEL_REVISION,
            "device": "cpu",
            "dimension": dimension,
            "max_seq_length": self.model.max_seq_length,
            "query_prefix": "query: ",
            "document_input": "passage: {title}\n{text}",
            "normalize_embeddings": True,
            "python": platform.python_version(),
            "packages": {
                package: version(package)
                for package in (
                    "sentence-transformers",
                    "transformers",
                    "torch",
                    "numpy",
                )
            },
            "results": results,
            "full_corpus": {
                "documents": len(all_documents),
                "embeddings": len(all_embeddings),
                "dimension": dimension,
            },
        }
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    unittest.main()

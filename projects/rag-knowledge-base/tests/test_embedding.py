"""验证问题、文档和片段编码的输入、长度限制与向量校验。"""

import unittest
from unittest.mock import Mock, call

import numpy as np

from rag_knowledge_base.chunking import chunk_document
from rag_knowledge_base.document import Document
from rag_knowledge_base.embedding import (
    encode_chunk,
    encode_chunks,
    encode_document,
    encode_documents,
    encode_query,
)

INVALID_EMBEDDINGS = (
    ([], "empty"),
    ([0.0, 0.0], "zero"),
    (["1", 0.0], "numbers"),
    ([None, 1.0], "numbers"),
    ([True, 0.0], "numbers"),
    ([1.0, np.nan], "finite"),
    ([1.0, np.inf], "finite"),
    ([1.0, -np.inf], "finite"),
    ([1.0], "dimension"),
    ([1.0, 0.0, 0.0], "dimension"),
)


class EncodeQueryTests(unittest.TestCase):
    def test_encodes_query_with_e5_prefix_and_normalization(self) -> None:
        vector = np.zeros(384, dtype=np.float32)
        vector[0] = 1.0
        model = Mock(spec=["encode", "get_embedding_dimension"])
        model.get_embedding_dimension.return_value = 384
        model.encode.return_value = vector
        query = "请求一直没有返回怎么办？"

        encode_query(model, query)

        model.encode.assert_called_once_with(
            f"query: {query}", normalize_embeddings=True
        )
        model.get_embedding_dimension.assert_called_once_with()

    def test_returns_numpy_vector_as_python_float_list(self) -> None:
        expected_values = [0.0, 0.0, -1.0]

        for dtype in (np.float32, np.float64):
            with self.subTest(dtype=dtype):
                model = Mock(spec=["encode", "get_embedding_dimension"])
                model.get_embedding_dimension.return_value = 3
                model.encode.return_value = np.asarray(expected_values, dtype=dtype)

                result = encode_query(model, "请求超时")

                self.assertIsInstance(result, list)
                self.assertEqual(result, expected_values)
                for value in result:
                    self.assertIs(type(value), float)

    def test_rejects_invalid_or_wrong_dimension_query_embeddings(self) -> None:
        for values, reason in INVALID_EMBEDDINGS:
            with self.subTest(values=values, reason=reason):
                model = Mock(spec=["encode", "get_embedding_dimension"])
                model.get_embedding_dimension.return_value = 2
                model.encode.return_value = np.asarray(values, dtype=object)

                with self.assertRaisesRegex(ValueError, reason):
                    encode_query(model, "请求超时")

                model.encode.assert_called_once_with(
                    "query: 请求超时", normalize_embeddings=True
                )


class EncodeDocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = Document(
            doc_id="network/timeout.md",
            title="超时",
            text="请求超时后有限重试。",
            source="network/timeout.md",
        )
        self.input_text = "passage: 超时\n请求超时后有限重试。"
        self.vector = np.zeros(384, dtype=np.float32)
        self.vector[9] = -1.0
        self.model = Mock(
            spec=["tokenizer", "encode", "max_seq_length", "get_embedding_dimension"]
        )
        self.model.max_seq_length = 512
        self.model.get_embedding_dimension.return_value = 384
        self.model.tokenizer.return_value = {"input_ids": [101, 102, 103]}
        self.model.encode.return_value = self.vector

    def test_encodes_complete_document_and_returns_python_float_list(self) -> None:
        result = encode_document(self.model, self.document)

        self.model.tokenizer.assert_called_once_with(self.input_text, truncation=False)
        self.model.encode.assert_called_once_with(
            self.input_text, normalize_embeddings=True
        )
        self.model.get_embedding_dimension.assert_called_once_with()
        self.assertIsInstance(result, list)
        self.assertEqual(result, self.vector.tolist())
        for value in result:
            self.assertIs(type(value), float)

    def test_accepts_document_at_model_token_limit(self) -> None:
        self.model.max_seq_length = 8
        self.model.tokenizer.return_value = {"input_ids": list(range(8))}

        result = encode_document(self.model, self.document)

        self.model.encode.assert_called_once_with(
            self.input_text, normalize_embeddings=True
        )
        self.assertEqual(result, self.vector.tolist())

    def test_rejects_document_over_model_token_limit_before_encoding(self) -> None:
        self.model.max_seq_length = 8
        self.model.tokenizer.return_value = {"input_ids": list(range(9))}

        with self.assertRaises(ValueError) as error:
            encode_document(self.model, self.document)

        self.assertIn(self.document.doc_id, str(error.exception))
        self.model.tokenizer.assert_called_once_with(self.input_text, truncation=False)
        self.model.encode.assert_not_called()

    def test_accepts_embedding_dimension_declared_by_model(self) -> None:
        self.model.get_embedding_dimension.return_value = 3
        self.model.encode.return_value = np.asarray([0.0, 0.0, -1.0])

        result = encode_document(self.model, self.document)

        self.assertEqual(result, [0.0, 0.0, -1.0])
        self.model.get_embedding_dimension.assert_called_once_with()

    def test_rejects_invalid_or_wrong_dimension_document_embeddings(self) -> None:
        self.model.get_embedding_dimension.return_value = 2

        for values, reason in INVALID_EMBEDDINGS:
            with self.subTest(values=values, reason=reason):
                self.model.reset_mock()
                self.model.encode.return_value = np.asarray(values, dtype=object)

                with self.assertRaisesRegex(ValueError, reason):
                    encode_document(self.model, self.document)

                self.model.tokenizer.assert_called_once_with(
                    self.input_text, truncation=False
                )
                self.model.encode.assert_called_once_with(
                    self.input_text, normalize_embeddings=True
                )


class EncodeDocumentsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.documents = [
            Document(
                doc_id="requests/timeout.md",
                title="超时",
                text="请求超时后有限重试。",
                source="requests/timeout.md",
            ),
            Document(
                doc_id="engineering/logging.md",
                title="日志",
                text="记录请求的结束原因。",
                source="engineering/logging.md",
            ),
        ]
        self.input_texts = [
            "passage: 超时\n请求超时后有限重试。",
            "passage: 日志\n记录请求的结束原因。",
        ]
        self.model = Mock(
            spec=["tokenizer", "encode", "max_seq_length", "get_embedding_dimension"]
        )
        self.model.max_seq_length = 512
        self.model.get_embedding_dimension.return_value = 384
        self.model.tokenizer.return_value = {"input_ids": [101, 102, 103]}

    def test_maps_each_document_id_to_its_encoded_vector(self) -> None:
        first_vector = np.zeros(384, dtype=np.float32)
        first_vector[3] = 1.0
        second_vector = np.zeros(384, dtype=np.float32)
        second_vector[7] = -1.0
        vectors_by_input = {
            self.input_texts[0]: first_vector,
            self.input_texts[1]: second_vector,
        }
        self.model.encode.side_effect = lambda text, normalize_embeddings: (
            vectors_by_input[text]
        )

        result = encode_documents(self.model, self.documents)

        self.assertEqual(
            result,
            {
                self.documents[0].doc_id: first_vector.tolist(),
                self.documents[1].doc_id: second_vector.tolist(),
            },
        )
        self.model.tokenizer.assert_has_calls(
            [call(text, truncation=False) for text in self.input_texts],
            any_order=True,
        )
        self.assertEqual(self.model.tokenizer.call_count, len(self.documents))
        self.model.encode.assert_has_calls(
            [call(text, normalize_embeddings=True) for text in self.input_texts],
            any_order=True,
        )
        self.assertEqual(self.model.encode.call_count, len(self.documents))

    def test_returns_empty_mapping_for_empty_documents(self) -> None:
        result = encode_documents(self.model, [])

        self.assertEqual(result, {})
        self.model.tokenizer.assert_not_called()
        self.model.encode.assert_not_called()

    def test_propagates_length_error_after_an_earlier_document_succeeds(self) -> None:
        self.model.max_seq_length = 8
        self.model.tokenizer.side_effect = [
            {"input_ids": list(range(8))},
            {"input_ids": list(range(9))},
        ]
        vector = np.zeros(384, dtype=np.float32)
        vector[3] = 1.0
        self.model.encode.return_value = vector

        with self.assertRaises(ValueError) as error:
            encode_documents(self.model, self.documents)

        self.assertIn(self.documents[1].doc_id, str(error.exception))
        self.assertEqual(
            self.model.tokenizer.call_args_list,
            [call(text, truncation=False) for text in self.input_texts],
        )
        self.model.encode.assert_called_once_with(
            self.input_texts[0], normalize_embeddings=True
        )

    def test_rejects_invalid_embedding_after_an_earlier_document_succeeds(self) -> None:
        self.model.get_embedding_dimension.return_value = 2

        for values, reason in INVALID_EMBEDDINGS:
            with self.subTest(values=values, reason=reason):
                self.model.reset_mock()
                self.model.encode.side_effect = [
                    np.asarray([1.0, 0.0]),
                    np.asarray(values, dtype=object),
                ]

                with self.assertRaisesRegex(ValueError, reason):
                    encode_documents(self.model, self.documents)

                self.assertEqual(
                    self.model.tokenizer.call_args_list,
                    [call(text, truncation=False) for text in self.input_texts],
                )
                self.assertEqual(
                    self.model.encode.call_args_list,
                    [
                        call(text, normalize_embeddings=True)
                        for text in self.input_texts
                    ],
                )


class ChunkEncodingTests(unittest.TestCase):
    def setUp(self) -> None:
        document = Document("guide.md", "指南", "one two", "guide.md")
        self.first, self.second = chunk_document(
            document, "v1", chunk_size=4, overlap=0
        )
        self.first_input = "passage: 指南\none "
        self.model = Mock(
            spec=["tokenizer", "encode", "max_seq_length", "get_embedding_dimension"]
        )
        self.model.max_seq_length = 3
        self.model.get_embedding_dimension.return_value = 2
        self.model.tokenizer.return_value = {"input_ids": [101, 5, 102]}

    def test_encodes_complete_inputs_and_maps_vectors_by_chunk_id(self) -> None:
        second_input = "passage: 指南\ntwo"
        self.model.encode.side_effect = [
            np.asarray([1.0, 0.0]),
            np.asarray([0.0, 1.0]),
        ]

        result = encode_chunks(self.model, [self.first, self.second])

        self.assertEqual(
            result,
            {self.first.chunk_id: [1.0, 0.0], self.second.chunk_id: [0.0, 1.0]},
        )
        self.assertEqual(
            self.model.tokenizer.call_args_list,
            [
                call(self.first_input, truncation=False),
                call(second_input, truncation=False),
            ],
        )
        self.assertEqual(
            self.model.encode.call_args_list,
            [
                call(self.first_input, normalize_embeddings=True),
                call(second_input, normalize_embeddings=True),
            ],
        )

    def test_rejects_an_overlength_chunk_before_encoding(self) -> None:
        self.model.tokenizer.return_value = {"input_ids": [101, 5, 6, 102]}

        with self.assertRaisesRegex(ValueError, "is too long: 4 > 3") as error:
            encode_chunks(self.model, [self.first, self.second])

        self.assertIn(f"Chunk {self.first.chunk_id}", str(error.exception))
        self.model.tokenizer.assert_called_once_with(self.first_input, truncation=False)
        self.model.encode.assert_not_called()

    def test_rejects_a_chunk_vector_with_the_wrong_dimension(self) -> None:
        self.model.encode.return_value = np.asarray([1.0])

        with self.assertRaisesRegex(ValueError, "Embedding dimension mismatch"):
            encode_chunk(self.model, self.first)


if __name__ == "__main__":
    unittest.main()

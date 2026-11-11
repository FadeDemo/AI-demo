from argparse import ArgumentParser
from pathlib import Path

from rag_knowledge_base.document import Document
from rag_knowledge_base.document_loader import load_documents
from rag_knowledge_base.keyword_retrieval import search_keywords


def print_result(results: list[tuple[Document, float]]) -> None:
    if results:
        for document, score in results:
            print(
                f"编号为 {document.doc_id} 的文档，标题是 {document.title}，"
                f"内容是 {document.text}，来源是 {document.source}，"
                f"匹配得分：{score}"
            )
    else:
        print("未找到匹配的文档")


def main() -> None:
    parser = ArgumentParser(description="载入文档集合")
    parser.add_argument("corpus_root", type=Path, help="语料根目录")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--doc-id", help="查看指定编号的文档")
    mode.add_argument(
        "--query",
        action="append",
        help="查询相关文档，可重复提供",
    )
    parser.add_argument("--method", choices=["keyword", "vector"], default="keyword")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    if args.k <= 0:
        parser.error("k must be a positive integer")
    documents = load_documents(args.corpus_root)
    if args.query is not None:
        try:
            if args.method == "keyword":
                for query in args.query:
                    results = search_keywords(documents, query, args.k)
                    if len(args.query) > 1:
                        print(f"查询 {query}")
                    print_result(results)
            elif args.method == "vector":
                from sentence_transformers import SentenceTransformer

                from rag_knowledge_base.embedding import encode_documents
                from rag_knowledge_base.vector_retrieval import search_vectors

                model = SentenceTransformer(
                    "intfloat/multilingual-e5-small",
                    revision="fd1525a9fd15316a2d503bf26ab031a61d056e98",
                    cache_folder=Path(__file__).resolve().parents[4]
                    / ".cache"
                    / "huggingface",
                    device="cpu",
                    token=False,
                )
                document_embeddings = encode_documents(model, documents)
                for query in args.query:
                    results = search_vectors(
                        model, documents, document_embeddings, query, args.k
                    )
                    if len(args.query) > 1:
                        print(f"查询 {query}")
                    print_result(results)
        except ValueError as error:
            parser.error(str(error))
    elif args.doc_id is not None:
        document = next((doc for doc in documents if doc.doc_id == args.doc_id), None)
        if document is not None:
            print(
                f"找到编号为 {args.doc_id} 的文档，标题是 {document.title}，"
                f"内容是 {document.text}，来源是 {document.source}"
            )
        else:
            parser.error(f"未找到编号为 {args.doc_id} 的文档")
    else:
        print(f"载入 {len(documents)} 个文档")
        for document in documents:
            print(document.doc_id)

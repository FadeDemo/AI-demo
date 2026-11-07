from argparse import ArgumentParser
from pathlib import Path

from rag_knowledge_base.document_loader import load_documents
from rag_knowledge_base.keyword_retrieval import search_keywords


def main() -> None:
    parser = ArgumentParser(description="载入文档集合")
    parser.add_argument("corpus_root", type=Path, help="语料根目录")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--doc-id", help="查看指定编号的文档")
    mode.add_argument("--query", help="查询相关文档")
    parser.add_argument("--method", choices=["keyword"], default="keyword")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    documents = load_documents(args.corpus_root)
    if args.query is not None:
        try:
            results = search_keywords(documents, args.query, args.k)
        except ValueError as error:
            parser.error(str(error))
        if results:
            for document, score in results:
                print(
                    f"编号为 {document.doc_id} 的文档，标题是 {document.title}，"
                    f"内容是 {document.text}，来源是 {document.source}，"
                    f"匹配得分：{score}"
                )
        else:
            print("未找到匹配的文档")
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

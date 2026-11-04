from argparse import ArgumentParser
from pathlib import Path

from rag_knowledge_base.document_loader import load_documents


def main() -> None:
    parser = ArgumentParser(description="载入文档集合")
    parser.add_argument("corpus_root", type=Path, help="语料根目录")
    parser.add_argument("--doc-id", help="查看指定编号的文档")
    args = parser.parse_args()
    documents = load_documents(args.corpus_root)
    if args.doc_id is not None:
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

import argparse
import json
from uuid import uuid4

from engineering_foundations.logging_config import configure_logging
from engineering_foundations.search import Document, search_documents

SAMPLE_DOCUMENTS = [
    Document(
        title="RAG 入门",
        content="RAG 在生成答案前从外部知识库检索相关内容。",
        source="rag.md",
    ),
    Document(
        title="日志基础",
        content="日志记录程序运行期间发生的事件。",
        source="logging.md",
    ),
    Document(
        title="基础测试",
        content="自动化测试把预期行为变成可以重复执行的检查。",
        source="testing.md",
    ),
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search a small document collection")
    parser.add_argument("query", help="case-insensitive text to find")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--json-logs", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    configure_logging(args.log_level, json_output=args.json_logs)
    request_id = f"req-{uuid4().hex[:8]}"
    results = search_documents(
        SAMPLE_DOCUMENTS,
        args.query,
        request_id=request_id,
        limit=args.limit,
    )
    output = [
        {
            "title": result.document.title,
            "source": result.document.source,
            "score": result.score,
        }
        for result in results
    ]
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

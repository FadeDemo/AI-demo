import logging
from uuid import uuid4

from engineering_foundations.logging_config import configure_logging

logger = logging.getLogger(__name__)


def query_external_index() -> None:
    raise TimeoutError("external index did not respond in time")


def main() -> int:
    try:
        query_external_index()
    except TimeoutError:
        logger.exception(
            "Error occurred while querying external index",
            extra={
                "event": "index_query_failed",
                "request_id": f"req-{uuid4().hex[:8]}",
            },
        )
        return 1
    return 0


if __name__ == "__main__":
    configure_logging()
    raise SystemExit(main())

import json
import logging

import pytest

from engineering_foundations.logging_config import JsonFormatter, configure_logging


def test_json_formatter_keeps_structured_context() -> None:
    record = logging.LogRecord(
        name="engineering_foundations.search",
        level=logging.INFO,
        pathname=__file__,
        lineno=12,
        msg="search completed",
        args=(),
        exc_info=None,
    )
    record.event = "search_completed"
    record.request_id = "req-json"
    record.result_count = 2

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["event"] == "search_completed"
    assert payload["request_id"] == "req-json"
    assert payload["result_count"] == 2


def test_configure_logging_rejects_unknown_level() -> None:
    with pytest.raises(ValueError, match="invalid log level"):
        configure_logging("verbose")

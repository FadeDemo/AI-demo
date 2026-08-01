import json
import logging
import time
from datetime import UTC, datetime

STANDARD_LOG_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
    """Format a log record as one JSON object without third-party packages."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(
            {
                key: value
                for key, value in record.__dict__.items()
                if key not in STANDARD_LOG_RECORD_FIELDS and not key.startswith("_")
            }
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    """Configure logging once at the application boundary."""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"invalid log level: {level}")

    handler = logging.StreamHandler()
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s "
            "event=%(event)s request_id=%(request_id)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
            defaults={"event": "-", "request_id": "-"},
        )
        formatter.converter = time.gmtime
        handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(numeric_level)

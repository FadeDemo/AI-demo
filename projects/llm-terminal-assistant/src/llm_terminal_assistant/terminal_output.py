import logging
import sys
from threading import RLock
from typing import TextIO


class TerminalOutput:
    """Coordinate text and log records written to one terminal stream."""

    def __init__(self, stream: TextIO | None = None):
        self.stream = stream
        self.at_line_start = True
        self._lock = RLock()

    def write_text(self, text: str) -> None:
        with self._lock:
            stream = self.stream if self.stream is not None else sys.stdout
            if text:
                stream.write(text)
                self.at_line_start = text.endswith("\n")
            stream.flush()

    def write_line(self, text: str = "") -> None:
        self.write_text(text + "\n")

    def write_log(self, message: str) -> None:
        with self._lock:
            prefix = "" if self.at_line_start else "\n"
            suffix = "" if message.endswith("\n") else "\n"
            self.write_text(prefix + message + suffix)


class TerminalLogHandler(logging.Handler):
    def __init__(self, output: TerminalOutput):
        super().__init__()
        self.output = output

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.output.write_log(self.format(record))
        except Exception:
            self.handleError(record)

import logging
import unittest
from io import StringIO

from llm_terminal_assistant.terminal_output import TerminalLogHandler, TerminalOutput


class TerminalOutputTests(unittest.TestCase):
    def test_interleaved_logs_preserve_order_and_only_add_required_separators(self):
        stream = StringIO()
        output = TerminalOutput(stream)
        output.write_log("before")
        output.write_text("你")
        output.write_text("好")
        output.write_text("")
        output.write_log("warning")
        output.write_log("another\n")
        output.write_text("继续\n")
        output.write_text("")
        output.write_log("after")
        output.write_text("last")
        output.write_line()
        output.write_log("next turn")
        self.assertEqual(
            stream.getvalue(),
            "before\n你好\nwarning\nanother\n继续\nafter\nlast\nnext turn\n",
        )

    def test_handler_formats_multiline_records_and_flushes_immediately(self):
        class ObservedStream(StringIO):
            def flush(self):
                self.flushed = self.getvalue()

        stream = ObservedStream()
        output = TerminalOutput(stream)
        handler = TerminalLogHandler(output)
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        try:
            output.write_text("partial")
            self.assertEqual(stream.flushed, "partial")
            handler.handle(
                logging.LogRecord(
                    "test", logging.WARNING, "", 0, "first\nsecond", (), None
                )
            )
            self.assertEqual(stream.flushed, "partial\n[WARNING] first\nsecond\n")
            output.write_text("continued")
            self.assertEqual(
                stream.flushed, "partial\n[WARNING] first\nsecond\ncontinued"
            )
        finally:
            handler.close()

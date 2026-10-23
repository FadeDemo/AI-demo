import unittest
from unittest.mock import Mock

from llm_terminal_assistant.request_control import (
    RequestStoppedError,
    RequestStopReason,
    check_request_deadline,
)


class RequestDeadlineTests(unittest.TestCase):
    def test_disabled_deadline_does_not_consult_clock(self):
        clock = Mock(side_effect=AssertionError("No deadline needs checking"))

        check_request_deadline(deadline_at=None, clock=clock)

        clock.assert_not_called()

    def test_time_before_deadline_is_allowed(self):
        check_request_deadline(deadline_at=110.0, clock=lambda: 109.5)

    def test_exact_or_exceeded_deadline_stops_request(self):
        for now in (110.0, 110.5):
            with self.subTest(now=now):
                with self.assertRaises(RequestStoppedError) as caught:
                    check_request_deadline(
                        deadline_at=110.0, clock=Mock(return_value=now)
                    )

                self.assertEqual(
                    caught.exception.reason, RequestStopReason.REQUEST_DEADLINE_EXCEEDED
                )


if __name__ == "__main__":
    unittest.main()

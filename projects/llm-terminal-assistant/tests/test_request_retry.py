import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from llm_terminal_assistant.config import RequestRetryConfig
from llm_terminal_assistant.model import ModelResponse, ModelResponseEndReason
from llm_terminal_assistant.request_control import (
    RequestStoppedError,
    RequestStopReason,
)
from llm_terminal_assistant.request_retry import (
    calculate_retry_delay,
    can_retry_response,
    wait_before_retry,
)


class RetryDelayTests(unittest.TestCase):
    def test_backoff_range_doubles_until_capped_before_random_selection(self):
        config = RequestRetryConfig(
            max_attempts=6, base_delay_seconds=2.0, max_delay_seconds=5.0
        )
        for attempt, expected_upper, expected_delay in (
            (1, 2.0, 1.0),
            (2, 4.0, 2.0),
            (3, 5.0, 2.5),
            (5, 5.0, 2.5),
        ):
            with self.subTest(attempt=attempt):
                uniform = Mock(side_effect=lambda low, high: (low + high) / 2)

                delay = calculate_retry_delay(config, attempt, None, uniform=uniform)

                uniform.assert_called_once_with(0.0, expected_upper)
                self.assertEqual(delay, expected_delay)

    def test_server_hint_sets_a_minimum_without_truncating_to_client_cap(self):
        config = RequestRetryConfig(base_delay_seconds=2.0, max_delay_seconds=5.0)
        for random_delay, hint, expected in (
            (0.0, None, 0.0),
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 1.0),
            (1.0, 0.5, 1.0),
            (1.0, 1.0, 1.0),
            (1.0, 1.5, 1.5),
            (1.0, 12.0, 12.0),
        ):
            with self.subTest(random_delay=random_delay, hint=hint):
                uniform = Mock(return_value=random_delay)

                delay = calculate_retry_delay(config, 1, hint, uniform=uniform)

                uniform.assert_called_once_with(0.0, 2.0)
                self.assertEqual(delay, expected)


class RetryResponseTests(unittest.TestCase):
    def test_failure_categories_with_empty_body_and_remaining_attempts(self):
        config = RequestRetryConfig()
        cases = (
            (ModelResponseEndReason.CONNECTION_FAILED, True),
            (ModelResponseEndReason.CONNECTION_TIMEOUT, True),
            (ModelResponseEndReason.READ_TIMEOUT, True),
            (ModelResponseEndReason.FIRST_EVENT_TIMEOUT, True),
            (ModelResponseEndReason.STREAM_IDLE_TIMEOUT, True),
            (ModelResponseEndReason.RATE_LIMITED, True),
            (ModelResponseEndReason.SERVICE_UNAVAILABLE, True),
            (ModelResponseEndReason.COMPLETED_NORMALLY, False),
            (ModelResponseEndReason.REQUEST_FAILED, False),
            (ModelResponseEndReason.REQUEST_CANCELLED, False),
            (ModelResponseEndReason.REQUEST_INCOMPLETE, False),
            (ModelResponseEndReason.MISSING_END_EVENT, False),
            (ModelResponseEndReason.STREAM_READ_FAILED, False),
            (ModelResponseEndReason.REQUEST_DEADLINE_EXCEEDED, False),
            (ModelResponseEndReason.AUTHENTICATION_FAILED, False),
            (ModelResponseEndReason.PERMISSION_DENIED, False),
            (ModelResponseEndReason.INVALID_REQUEST, False),
        )
        for reason, expected in cases:
            with self.subTest(reason=reason):
                response = ModelResponse(text="", reason=reason, usage=None)

                self.assertIs(can_retry_response(response, 1, config), expected)

    def test_attempt_limit_includes_the_first_send(self):
        response = ModelResponse(
            text="", reason=ModelResponseEndReason.SERVICE_UNAVAILABLE, usage=None
        )
        for max_attempts, attempt, expected in (
            (3, 1, True),
            (3, 2, True),
            (3, 3, False),
            (3, 4, False),
            (1, 1, False),
        ):
            with self.subTest(max_attempts=max_attempts, attempt=attempt):
                config = RequestRetryConfig(max_attempts=max_attempts)

                self.assertIs(can_retry_response(response, attempt, config), expected)

    def test_any_displayed_text_blocks_retry_even_for_retryable_failures(self):
        config = RequestRetryConfig()
        for reason in (
            ModelResponseEndReason.READ_TIMEOUT,
            ModelResponseEndReason.RATE_LIMITED,
            ModelResponseEndReason.SERVICE_UNAVAILABLE,
        ):
            for text in ("Partial answer", " ", "\n", "\t"):
                with self.subTest(reason=reason, text=text):
                    response = ModelResponse(text=text, reason=reason, usage=None)

                    self.assertFalse(can_retry_response(response, 1, config))


class RetryWaitTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_for_full_delay_including_zero_with_or_without_deadline(self):
        for deadline in (None, 15.0):
            for delay in (0.0, 2.0):
                with self.subTest(deadline=deadline, delay=delay):
                    sleep = AsyncMock(return_value=None)
                    clock = Mock(side_effect=[10.0, 10.0 + delay])

                    result = await wait_before_retry(delay, deadline, clock, sleep)

                    self.assertIsNone(result)
                    sleep.assert_awaited_once_with(delay)

    async def test_rejects_expired_or_insufficient_time_before_waiting(self):
        for deadline, expected_reason in (
            (9.0, RequestStopReason.REQUEST_DEADLINE_EXCEEDED),
            (10.0, RequestStopReason.REQUEST_DEADLINE_EXCEEDED),
            (11.0, RequestStopReason.INSUFFICIENT_RETRY_TIME),
            (12.0, RequestStopReason.INSUFFICIENT_RETRY_TIME),
        ):
            with self.subTest(deadline=deadline):
                sleep = AsyncMock(return_value=None)

                with self.assertRaises(RequestStoppedError) as caught:
                    await wait_before_retry(2.0, deadline, lambda: 10.0, sleep)

                self.assertEqual(caught.exception.reason, expected_reason)
                sleep.assert_not_called()

    async def test_checks_deadline_again_after_wait_returns(self):
        for finished_at in (15.0, 16.0):
            with self.subTest(finished_at=finished_at):
                sleep = AsyncMock(return_value=None)
                clock = Mock(side_effect=[10.0, finished_at])

                with self.assertRaises(RequestStoppedError) as caught:
                    await wait_before_retry(2.0, 15.0, clock, sleep)

                sleep.assert_awaited_once_with(2.0)
                self.assertEqual(
                    caught.exception.reason, RequestStopReason.REQUEST_DEADLINE_EXCEEDED
                )

    async def test_deadline_interrupts_pending_wait_and_reports_request_stop(self):
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        finished = asyncio.Event()
        pending_wait = loop.create_future()
        real_timeout = asyncio.timeout
        timeouts = []

        def capture_timeout(seconds):
            context = real_timeout(seconds)
            timeouts.append(context)
            return context

        async def pending_sleep(delay):
            started.set()
            try:
                await pending_wait
            finally:
                finished.set()

        sleep = AsyncMock(side_effect=pending_sleep)
        with patch(
            "llm_terminal_assistant.request_retry.asyncio.timeout",
            side_effect=capture_timeout,
        ) as timeout:
            task = asyncio.create_task(
                wait_before_retry(2.0, 15.0, lambda: 10.0, sleep),
                name="test-retry-wait-deadline",
            )
            try:
                # 先确认等待已挂起，再让真实超时上下文到期；无需真实睡眠。
                async with real_timeout(5.0):
                    await started.wait()
                    self.assertFalse(task.done())
                    timeout.assert_called_once_with(5.0)
                    timeouts[0].reschedule(loop.time() - 1.0)
                    with self.assertRaises(RequestStoppedError) as caught:
                        await task
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        self.assertEqual(
            caught.exception.reason, RequestStopReason.REQUEST_DEADLINE_EXCEEDED
        )
        self.assertIsInstance(caught.exception.__cause__, TimeoutError)
        self.assertTrue(timeouts[0].expired())
        self.assertTrue(pending_wait.cancelled())
        self.assertTrue(finished.is_set())
        sleep.assert_awaited_once_with(2.0)

    async def test_user_cancellation_interrupts_wait_and_propagates(self):
        for deadline in (None, 15.0):
            with self.subTest(deadline=deadline):
                started = asyncio.Event()
                finished = asyncio.Event()
                pending_wait = asyncio.get_running_loop().create_future()

                async def pending_sleep(
                    delay,
                    *,
                    started=started,
                    finished=finished,
                    pending_wait=pending_wait,
                ):
                    started.set()
                    try:
                        await pending_wait
                    finally:
                        finished.set()

                sleep = AsyncMock(side_effect=pending_sleep)
                task = asyncio.create_task(
                    wait_before_retry(2.0, deadline, lambda: 10.0, sleep),
                    name="test-retry-wait-cancellation",
                )
                try:
                    async with asyncio.timeout(5.0):
                        await started.wait()
                        self.assertFalse(task.done())
                        self.assertTrue(task.cancel())
                        with self.assertRaises(asyncio.CancelledError):
                            await task
                finally:
                    if not task.done():
                        task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

                self.assertTrue(task.cancelled())
                self.assertTrue(pending_wait.cancelled())
                self.assertTrue(finished.is_set())
                sleep.assert_awaited_once_with(2.0)

    async def test_default_zero_delay_still_allows_cancellation(self):
        clock = Mock(return_value=10.0)
        task = asyncio.create_task(
            wait_before_retry(0.0, None, clock),
            name="test-retry-zero-delay-cancellation",
        )
        # 任务先运行到默认 sleep(0) 让出执行权，再执行取消回调。
        cancel_handle = asyncio.get_running_loop().call_soon(task.cancel)
        try:
            async with asyncio.timeout(5.0):
                with self.assertRaises(asyncio.CancelledError):
                    await task
        finally:
            cancel_handle.cancel()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        clock.assert_called_once_with()
        self.assertTrue(task.cancelled())


if __name__ == "__main__":
    unittest.main()

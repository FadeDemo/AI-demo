import asyncio
import json
import logging
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import UTC, datetime
from io import StringIO
from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import DEFAULT, AsyncMock, Mock, patch

from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import DummyInput, create_pipe_input
from prompt_toolkit.output import DummyOutput

from llm_terminal_assistant.adapter.fake_client import FakeClient
from llm_terminal_assistant.adapter.fake_model import (
    CodePointTokenCounter,
    FakeModelRequestEncoder,
)
from llm_terminal_assistant.budgeter import (
    Budgeter,
    BudgetRejectedError,
    BudgetRejectionReason,
)
from llm_terminal_assistant.cli import (
    main,
    run_conversation,
    send_conversation_turn,
    send_stream_conversation_turn,
    talk,
)
from llm_terminal_assistant.config import ModelConfig, RequestTimeoutConfig
from llm_terminal_assistant.conversation import ConversationTurn
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import (
    FAKE_MODEL_PROFILE,
    InputTokensDetails,
    ModelLimits,
    ModelRequest,
    ModelResponse,
    ModelResponseEndReason,
    ModelResponseError,
    ModelResponseIncompleteDetails,
    ModelUsage,
    OutputTokensDetails,
)
from llm_terminal_assistant.stream.events import EndEvent, TextDeltaEvent, UsageEvent
from llm_terminal_assistant.tools.errors import ToolLoopStoppedError, ToolLoopStopReason
from llm_terminal_assistant.tools.factory import create_default_tool_registry
from llm_terminal_assistant.tools.loop import ToolLoopLimits
from llm_terminal_assistant.tools.protocol import ToolCallRequest, ToolCallResult


def make_response(text: str, calls: list[ToolCallRequest] | None = None):
    return ModelResponse(
        text=text,
        reason=ModelResponseEndReason.COMPLETED_NORMALLY,
        usage=ModelUsage(
            input_tokens=0,
            input_tokens_details=InputTokensDetails(0, 0),
            output_tokens=0,
            output_tokens_details=OutputTokensDetails(0),
            total_tokens=0,
        ),
        tool_calls=[] if calls is None else calls,
    )


def configure_prompt_session(mock_session, prompts):
    mock_session.return_value.app = SimpleNamespace(input=DummyInput(), ttimeoutlen=0.5)
    mock_session.return_value.prompt_async.side_effect = prompts


class StreamConversationTurnTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = ModelConfig(
            api_key="",
            base_url="",
            model="fake-model",
            model_profile=FAKE_MODEL_PROFILE,
        )
        self.budgeter = Budgeter(
            token_counter=CodePointTokenCounter(),
            request_encoder=FakeModelRequestEncoder(),
            model_limits=ModelLimits(context_window_tokens=100_000),
            safety_margin_tokens=0,
        )
        self.system = Message(role="system", content="You are a helpful assistant.")
        self.user = Message(role="user", content="question")

    async def test_stream_turn_checks_budget_and_displays_each_delta_before_reading_more(
        self,
    ):
        usage = make_response("").usage
        client = FakeClient(
            self.config,
            scripted_events=[
                TextDeltaEvent(delta="first "),
                TextDeltaEvent(delta="second\n"),
                TextDeltaEvent(delta="third"),
                UsageEvent(usage=usage),
                EndEvent(
                    reason=ModelResponseEndReason.COMPLETED_NORMALLY,
                    error=None,
                    incomplete_details=None,
                ),
            ],
        )
        history = [
            ConversationTurn(
                items=[Message("user", "previous"), Message("assistant", "answer")]
            )
        ]
        displayed = []
        upstream_send = client.send_stream

        async def observed_stream(request):
            self.assertEqual(budget_check.call_args.args, (request,))
            upstream = upstream_send(request)
            expected_display = []
            try:
                async for event in upstream:
                    if isinstance(event, TextDeltaEvent):
                        expected_display.append(event.delta)
                    yield event
                    self.assertEqual(displayed, expected_display)
            finally:
                await upstream.aclose()

        with (
            patch.object(
                self.budgeter, "check", wraps=self.budgeter.check
            ) as budget_check,
            patch.object(
                client, "send_stream", side_effect=observed_stream
            ) as send_stream,
            patch.object(client, "send", wraps=client.send) as send,
        ):
            response, trim_result = await send_stream_conversation_turn(
                client=client,
                budgeter=self.budgeter,
                system_message=self.system,
                completed_turns=history,
                current_user_message=self.user,
                reserved_output_tokens=128,
                min_reserved_recent_turns=1,
                reasoning_effort="none",
                temperature=0.4,
                top_p=0.8,
                display_text=displayed.append,
            )

        expected_request = ModelRequest(
            input=[self.system, *history[0].items, self.user],
            reserved_output_tokens=128,
            reasoning_effort="none",
            temperature=0.4,
            top_p=0.8,
        )
        self.assertEqual(trim_result.request, expected_request)
        budget_check.assert_called_once_with(trim_result.request)
        send_stream.assert_called_once_with(trim_result.request)
        send.assert_not_called()
        self.assertEqual(client.requests, [expected_request])
        self.assertEqual(trim_result.retained_completed_turns, history)
        self.assertEqual(trim_result.dropped_completed_turns_count, 0)
        self.assertEqual(displayed, ["first ", "second\n", "third"])
        self.assertEqual(response.text, "first second\nthird")
        self.assertEqual(response.reason, ModelResponseEndReason.COMPLETED_NORMALLY)
        self.assertIs(response.usage, usage)
        self.assertEqual(response.tool_calls, [])

    async def test_total_timing_includes_preparation_reading_and_cleanup(self):
        async def exercise(expected_reason, first_text):
            now = [100.0]
            closed = []
            client = FakeClient(self.config)
            encode = self.budgeter.request_encoder.encode_request

            def timed_encode(request):
                now[0] += 2.0
                return encode(request)

            async def timed_stream(request):
                try:
                    now[0] += 1.0
                    yield TextDeltaEvent("")
                    now[0] += 1.0
                    yield UsageEvent(make_response("").usage)
                    now[0] += 1.0
                    if first_text is not None:
                        yield TextDeltaEvent(first_text)
                    now[0] += 2.0
                    if first_text is not None:
                        yield TextDeltaEvent("later")
                    if expected_reason == ModelResponseEndReason.STREAM_READ_FAILED:
                        raise RuntimeError("read failed")
                    if expected_reason == ModelResponseEndReason.COMPLETED_NORMALLY:
                        yield EndEvent(expected_reason, None, None)
                finally:
                    now[0] += 4.0
                    closed.append(True)

            with (
                patch.object(
                    self.budgeter.request_encoder,
                    "encode_request",
                    side_effect=timed_encode,
                ),
                patch.object(client, "send_stream", side_effect=timed_stream),
            ):
                response, _ = await send_stream_conversation_turn(
                    client=client,
                    budgeter=self.budgeter,
                    system_message=self.system,
                    completed_turns=[],
                    current_user_message=self.user,
                    reserved_output_tokens=128,
                    min_reserved_recent_turns=1,
                    display_text=lambda delta: None,
                    clock=lambda: now[0],
                )

            self.assertEqual(response.reason, expected_reason)
            self.assertEqual(
                response.text, "" if first_text is None else first_text + "later"
            )
            self.assertEqual(closed, [True])
            self.assertEqual(response.timing.total_seconds, 11.0)
            self.assertEqual(
                response.timing.ttft_seconds, None if first_text is None else 5.0
            )

        for reason in (
            ModelResponseEndReason.COMPLETED_NORMALLY,
            ModelResponseEndReason.STREAM_READ_FAILED,
            ModelResponseEndReason.MISSING_END_EVENT,
        ):
            for first_text in ("partial", " \n", None):
                with self.subTest(reason=reason, first_text=first_text):
                    await exercise(reason, first_text)

    async def test_total_deadline_includes_preparation_and_stops_before_first_read(
        self,
    ):
        async def exercise(preparation_seconds):
            now = [100.0]
            client = FakeClient(
                self.config,
                scripted_events=[
                    EndEvent(ModelResponseEndReason.COMPLETED_NORMALLY, None, None)
                ],
            )
            encode = self.budgeter.request_encoder.encode_request
            send_stream = client.send_stream
            streams = []
            display = Mock()

            def timed_encode(request):
                now[0] += preparation_seconds
                return encode(request)

            def record_stream(request):
                stream = send_stream(request)
                streams.append(stream)
                return stream

            with (
                patch.object(
                    self.budgeter.request_encoder,
                    "encode_request",
                    side_effect=timed_encode,
                ),
                patch.object(client, "send_stream", side_effect=record_stream),
            ):
                response, _ = await send_stream_conversation_turn(
                    client=client,
                    budgeter=self.budgeter,
                    system_message=self.system,
                    completed_turns=[],
                    current_user_message=self.user,
                    reserved_output_tokens=128,
                    min_reserved_recent_turns=1,
                    display_text=display,
                    clock=lambda: now[0],
                    request_timeout_config=RequestTimeoutConfig(10.0, 30.0, 30.0, 5.0),
                )

            self.assertEqual(
                response.reason, ModelResponseEndReason.REQUEST_DEADLINE_EXCEEDED
            )
            self.assertEqual(response.error.code, "request_deadline_exceeded")
            self.assertEqual(client.requests, [])
            self.assertEqual(len(streams), 1)
            self.assertIsNone(streams[0].ag_frame)
            display.assert_not_called()
            self.assertEqual(response.text, "")
            self.assertIsNone(response.usage)
            self.assertIsNone(response.timing.ttft_seconds)
            self.assertEqual(response.timing.total_seconds, preparation_seconds)

        for preparation_seconds in (5.0, 6.0):
            with self.subTest(preparation_seconds=preparation_seconds):
                await exercise(preparation_seconds)

    async def test_total_deadline_is_not_reset_by_activity_and_includes_cleanup(self):
        now = [100.0]
        client = FakeClient(self.config)
        usage = make_response("").usage
        reads, displayed, closures = [], [], []
        events = [
            (101.0, TextDeltaEvent("first")),
            (102.0, TextDeltaEvent("")),
            (103.0, UsageEvent(usage)),
            (104.0, TextDeltaEvent("last")),
            (105.0, TextDeltaEvent("must not read")),
        ]

        async def active_stream(request):
            client.requests.append(request)
            try:
                for received_at, event in events:
                    now[0] = received_at
                    reads.append(event)
                    yield event
            finally:
                await asyncio.sleep(0)
                now[0] += 1.0
                closures.append(True)

        def display(delta):
            displayed.append(delta)
            now[0] += 1.0

        with patch.object(client, "send_stream", side_effect=active_stream):
            response, _ = await send_stream_conversation_turn(
                client=client,
                budgeter=self.budgeter,
                system_message=self.system,
                completed_turns=[],
                current_user_message=self.user,
                reserved_output_tokens=128,
                min_reserved_recent_turns=1,
                display_text=display,
                clock=lambda: now[0],
                request_timeout_config=RequestTimeoutConfig(10.0, 30.0, 30.0, 5.0),
            )

        self.assertEqual(
            response.reason, ModelResponseEndReason.REQUEST_DEADLINE_EXCEEDED
        )
        self.assertEqual(response.error.code, "request_deadline_exceeded")
        self.assertEqual(response.text, "firstlast")
        self.assertIs(response.usage, usage)
        self.assertEqual(response.timing.ttft_seconds, 1.0)
        self.assertEqual(response.timing.total_seconds, 6.0)
        self.assertEqual(displayed, ["first", "", "last"])
        self.assertEqual(reads, [event for _, event in events[:-1]])
        self.assertEqual(closures, [True])
        self.assertEqual(len(client.requests), 1)

    async def test_budget_rejection_prevents_stream_creation_and_display(self):
        self.budgeter.model_limits = ModelLimits(context_window_tokens=1)
        client = FakeClient(self.config)
        displayed = Mock()

        with (
            patch.object(
                client, "send_stream", wraps=client.send_stream
            ) as send_stream,
            patch.object(client, "send", wraps=client.send) as send,
            self.assertRaises(BudgetRejectedError) as caught,
        ):
            await send_stream_conversation_turn(
                client=client,
                budgeter=self.budgeter,
                system_message=self.system,
                completed_turns=[],
                current_user_message=self.user,
                reserved_output_tokens=128,
                min_reserved_recent_turns=1,
                display_text=displayed,
            )

        self.assertEqual(
            caught.exception.reason, BudgetRejectionReason.CONTEXT_WINDOW_EXCEEDED
        )
        send_stream.assert_not_called()
        send.assert_not_called()
        displayed.assert_not_called()
        self.assertEqual(client.requests, [])


class TalkTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = ModelConfig(
            api_key="",
            base_url="",
            model="fake-model",
            model_profile=FAKE_MODEL_PROFILE,
            default_reserved_output_tokens=128,
        )
        self.encoder = Mock(wraps=FakeModelRequestEncoder())
        self.budgeter = Budgeter(
            token_counter=CodePointTokenCounter(),
            request_encoder=self.encoder,
            model_limits=ModelLimits(context_window_tokens=100_000),
            safety_margin_tokens=0,
        )
        self.clock = Mock(return_value=datetime(2026, 10, 4, 4, 0, tzinfo=UTC))
        self.registry = create_default_tool_registry(clock=self.clock)

    async def run_talk(
        self,
        prompts: list[str],
        responses: list[ModelResponse],
        *,
        expected_budget_checks: int | None = None,
    ):
        client = FakeClient(self.config, scripted_responses=responses)
        output = StringIO()
        with (
            patch(
                "llm_terminal_assistant.cli.PromptSession", autospec=True
            ) as prompt_session,
            patch(
                "llm_terminal_assistant.cli.create_default_tool_registry",
                return_value=self.registry,
            ) as create_registry,
            redirect_stdout(output),
        ):
            configure_prompt_session(prompt_session, [*prompts, "exit"])
            await talk(client, self.config, self.budgeter)

        prompt_session.assert_called_once_with()
        create_registry.assert_called_once_with()
        checked_requests = [
            call.args[0] for call in self.encoder.encode_request.call_args_list
        ]
        if expected_budget_checks is None:
            self.assertEqual(checked_requests, client.requests)
        else:
            self.assertEqual(len(checked_requests), expected_budget_checks)
        for request in client.requests:
            self.assertTrue(any(request is checked for checked in checked_requests))
        for request in client.requests:
            self.assertEqual(request.tools, self.registry.get_tool_list())
        return client, output.getvalue()

    async def run_stream_talk(self, events, prompts):
        config = replace(self.config, stream_output_enabled=True)
        client = FakeClient(config, scripted_events=events)
        output = StringIO()
        upstream_send = client.send_stream

        async def observed_stream(request):
            self.assertTrue(output.getvalue().endswith("Model Response: \n"))
            upstream = upstream_send(request)
            try:
                async for event in upstream:
                    before = output.getvalue()
                    yield event
                    if isinstance(event, TextDeltaEvent):
                        self.assertEqual(output.getvalue(), before + event.delta)
                    elif isinstance(event, UsageEvent):
                        self.assertEqual(output.getvalue(), before)
            finally:
                await upstream.aclose()

        with (
            patch(
                "llm_terminal_assistant.cli.PromptSession", autospec=True
            ) as prompt_session,
            patch(
                "llm_terminal_assistant.cli.create_default_tool_registry",
                return_value=self.registry,
            ),
            patch.object(
                client, "send_stream", side_effect=observed_stream
            ) as send_stream,
            patch.object(client, "send", wraps=client.send) as send,
            redirect_stdout(output),
        ):
            configure_prompt_session(prompt_session, [*prompts, "exit"])
            await talk(client, config, self.budgeter)

        prompt_session.assert_called_once_with()
        self.assertEqual(send_stream.call_count, len(prompts))
        send.assert_not_called()
        self.clock.assert_not_called()
        self.assertEqual(
            [call.args[0] for call in self.encoder.encode_request.call_args_list],
            client.requests,
        )
        for request in client.requests:
            self.assertEqual(request.tools, [])
        return client, output.getvalue()

    async def test_cancel_keys_cancel_pending_read_and_next_turn_completes(self):
        usage = make_response("").usage
        for key_input in ("\x1b", "\x03"):
            for events in ([], [TextDeltaEvent("partial answer"), UsageEvent(usage)]):
                with self.subTest(key_input=key_input, events=events):
                    await self._assert_keyboard_cancellation(events, key_input)

    async def _assert_keyboard_cancellation(self, events, key_input):
        usage = make_response("").usage
        config = replace(self.config, stream_output_enabled=True)
        client = FakeClient(config)
        waiting = asyncio.Event()
        closures, responses = [], []
        output = StringIO()

        async def waiting_stream(request):
            client.requests.append(request)
            if len(client.requests) > 1:
                self.assertEqual(closures, [True])
                yield TextDeltaEvent("next answer")
                yield EndEvent(ModelResponseEndReason.COMPLETED_NORMALLY, None, None)
                return
            try:
                for event in events:
                    yield event
                waiting.set()
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                closures.append(True)

        async def observed_turn(*args, **kwargs):
            result = await send_stream_conversation_turn(*args, **kwargs)
            responses.append(result[0])
            return result

        with (
            create_pipe_input() as terminal_input,
            patch("llm_terminal_assistant.cli.PromptSession") as session,
            patch.object(client, "send_stream", side_effect=waiting_stream),
            patch(
                "llm_terminal_assistant.cli.send_stream_conversation_turn",
                side_effect=observed_turn,
            ),
            redirect_stdout(output),
        ):
            session.return_value = SimpleNamespace(
                app=SimpleNamespace(input=terminal_input, ttimeoutlen=0),
                prompt_async=AsyncMock(side_effect=["first", "second", "exit"]),
            )
            task = asyncio.create_task(talk(client, config, self.budgeter))
            try:
                async with asyncio.timeout(2):
                    await waiting.wait()
                    terminal_input.send_text(key_input)
                    await task
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        self.assertEqual(closures, [True])
        self.assertEqual(len(client.requests), 2)
        self.assertEqual(
            [response.reason for response in responses],
            [
                ModelResponseEndReason.REQUEST_CANCELLED,
                ModelResponseEndReason.COMPLETED_NORMALLY,
            ],
        )
        self.assertEqual(responses[0].text, "partial answer" if events else "")
        self.assertEqual(responses[0].usage, usage if events else None)
        self.assertIsNone(responses[0].error)
        self.assertEqual(output.getvalue().count("Request was cancelled."), 1)
        self.assertIn("next answer\nExiting...", output.getvalue())

    async def test_pending_keyboard_timer_is_cancelled_when_each_turn_ends(self):
        for fail_read in (False, True):
            with self.subTest(fail_read=fail_read):
                await self._assert_keyboard_timer_cleanup(fail_read)

    async def _assert_keyboard_timer_cleanup(self, fail_read):
        config = replace(self.config, stream_output_enabled=True)
        client = FakeClient(config)
        handles = []
        loop = asyncio.get_running_loop()
        original_call_later = loop.call_later

        def record_timer(delay, callback, *args, **kwargs):
            handle = original_call_later(delay, callback, *args, **kwargs)
            if callback.__name__ == "flush_pending_keys":
                handles.append(handle)
            return handle

        async def stream(request):
            if fail_read:
                raise RuntimeError("stream failed")
            yield EndEvent(ModelResponseEndReason.COMPLETED_NORMALLY, None, None)

        with (
            patch("llm_terminal_assistant.cli.PromptSession", autospec=True) as session,
            patch.object(client, "send_stream", side_effect=stream),
            patch.object(loop, "call_later", side_effect=record_timer),
            redirect_stdout(StringIO()),
        ):
            configure_prompt_session(session, ["first", "second", "exit"])
            session.return_value.app.ttimeoutlen = 3600
            try:
                await talk(client, config, self.budgeter)
                self.assertEqual(len(handles), 2)
                self.assertTrue(all(handle.cancelled() for handle in handles))
            finally:
                for handle in handles:
                    handle.cancel()

    async def test_streaming_displays_deltas_once_and_replays_assembled_history(self):
        completed = EndEvent(ModelResponseEndReason.COMPLETED_NORMALLY, None, None)
        client, output = await self.run_stream_talk(
            [
                TextDeltaEvent(""),
                UsageEvent(make_response("").usage),
                TextDeltaEvent("first "),
                TextDeltaEvent("second\n"),
                TextDeltaEvent("third"),
                completed,
                TextDeltaEvent("next answer"),
                completed,
            ],
            ["First question", "Next question"],
        )

        self.assertEqual(
            output,
            "Please enter your prompt (type 'exit' to quit):\n\n"
            "Model Response: \nfirst second\nthird\n"
            "Model Response: \nnext answer\nExiting...\n",
        )
        self.assertEqual(
            client.requests[1].input,
            [
                Message("system", "You are a helpful assistant."),
                Message("user", "First question"),
                Message("assistant", "first second\nthird"),
                Message("user", "Next question"),
            ],
        )

    async def test_streaming_preserves_model_newlines_and_always_adds_ui_separator(
        self,
    ):
        for text in ("", "answer", "answer\n", "answer\n\n"):
            with self.subTest(text=text):
                self.encoder.reset_mock()
                _, output = await self.run_stream_talk(
                    [
                        TextDeltaEvent(text),
                        EndEvent(ModelResponseEndReason.COMPLETED_NORMALLY, None, None),
                    ],
                    ["question"],
                )

                self.assertEqual(
                    output,
                    "Please enter your prompt (type 'exit' to quit):\n\n"
                    "Model Response: \n" + text + "\nExiting...\n",
                )

    async def test_streaming_keeps_partial_text_and_displays_terminal_status_on_new_line(
        self,
    ):
        cases = [
            (
                EndEvent(
                    ModelResponseEndReason.REQUEST_FAILED,
                    ModelResponseError("server_error", "Generation failed."),
                    None,
                ),
                "Request was failed: [server_error] Generation failed.",
            ),
            (
                EndEvent(ModelResponseEndReason.REQUEST_CANCELLED, None, None),
                "Request was cancelled.",
            ),
            (
                EndEvent(
                    ModelResponseEndReason.REQUEST_INCOMPLETE,
                    None,
                    ModelResponseIncompleteDetails("max_output_tokens"),
                ),
                "Request was incomplete: max_output_tokens",
            ),
            (
                None,
                "Streaming response ended without a terminal event. "
                "The answer may be incomplete.",
            ),
        ]
        for terminal, notice in cases:
            with self.subTest(terminal=terminal):
                self.encoder.reset_mock()
                events = [TextDeltaEvent("partial answer")]
                if terminal is not None:
                    events.append(terminal)
                _, output = await self.run_stream_talk(events, ["question"])

                self.assertEqual(
                    output,
                    "Please enter your prompt (type 'exit' to quit):\n\n"
                    f"Model Response: \npartial answer\n{notice}\nExiting...\n",
                )

    async def test_stream_connection_timeout_displays_notice_without_answer_text(self):
        _, output = await self.run_stream_talk(
            [
                EndEvent(
                    ModelResponseEndReason.CONNECTION_TIMEOUT,
                    ModelResponseError("connection_timeout", "Request timed out."),
                    None,
                ),
            ],
            ["question"],
        )

        self.assertEqual(
            output,
            "Please enter your prompt (type 'exit' to quit):\n\n"
            "Model Response: \n\n"
            "Connection timed out. Could not connect to the model service.\n"
            "Exiting...\n",
        )

    async def _assert_pending_stream_timeout(
        self,
        *,
        timeout_config,
        events,
        expected_waits,
        expected_reason,
        error_message,
        notice,
    ):
        config = replace(
            self.config,
            stream_output_enabled=True,
            request_timeout_config=timeout_config,
        )
        client = FakeClient(config)
        loop = asyncio.get_running_loop()
        pending_read = loop.create_future()
        timeouts, steps, responses = [], [], []
        output = StringIO()

        def record_timeout(seconds):
            context = asyncio.timeout(seconds)
            timeouts.append(context)
            return context

        async def waiting_stream(request):
            client.requests.append(request)
            try:
                for event in events:
                    yield event
                self.assertEqual(len(timeouts), len(events) + 1)
                # 等待读取挂起后，调度真实 timeout 到期，不注入事件或超时异常。
                loop.call_soon(timeouts[-1].reschedule, loop.time())
                steps.append("reading")
                await pending_read
                steps.append("read completed")
                yield TextDeltaEvent("must not display")
            finally:
                steps.append("cleanup started")
                await asyncio.sleep(0)
                steps.append("closed")

        async def observed_turn(*args, **kwargs):
            result = await send_stream_conversation_turn(
                *args, **kwargs, clock=lambda: 100.0
            )
            responses.append(result[0])
            steps.append("turn returned")
            return result

        with (
            patch(
                "llm_terminal_assistant.cli.PromptSession", autospec=True
            ) as prompt_session,
            patch(
                "llm_terminal_assistant.stream.consumer.timeout",
                side_effect=record_timeout,
            ) as timeout,
            patch(
                "llm_terminal_assistant.cli.send_stream_conversation_turn",
                side_effect=observed_turn,
            ),
            patch.object(
                client, "send_stream", side_effect=waiting_stream
            ) as send_stream,
            patch.object(client, "send", wraps=client.send) as send,
            redirect_stdout(output),
        ):
            configure_prompt_session(prompt_session, ["question", "exit"])
            await talk(client, config, self.budgeter)

        self.assertEqual(
            [call.args[0] for call in timeout.call_args_list], expected_waits
        )
        self.assertEqual(
            [context.expired() for context in timeouts],
            [False] * len(events) + [True],
        )
        self.assertTrue(pending_read.cancelled())
        self.assertEqual(
            steps, ["reading", "cleanup started", "closed", "turn returned"]
        )
        self.assertEqual(len(responses), 1)
        response = responses[0]
        self.assertEqual(response.reason, expected_reason)
        self.assertEqual(
            response.error,
            ModelResponseError(code=expected_reason, message=error_message),
        )
        expected_text = "".join(
            event.delta for event in events if isinstance(event, TextDeltaEvent)
        )
        expected_usage = next(
            (
                event.usage
                for event in reversed(events)
                if isinstance(event, UsageEvent)
            ),
            None,
        )
        self.assertEqual(response.text, expected_text)
        self.assertIs(response.usage, expected_usage)
        self.assertEqual(response.timing.ttft_seconds, 0.0 if expected_text else None)
        self.assertEqual(len(client.requests), 1)
        send_stream.assert_called_once_with(client.requests[0])
        send.assert_not_called()
        self.assertEqual(
            output.getvalue(),
            "Please enter your prompt (type 'exit' to quit):\n\n"
            f"Model Response: \n{expected_text}\n{notice}\n"
            "Exiting...\n",
        )

    async def test_first_event_timeout_interrupts_pending_read_and_displays_notice(
        self,
    ):
        await self._assert_pending_stream_timeout(
            timeout_config=RequestTimeoutConfig(10.0, 3.5, 30.0, 120.0),
            events=[],
            expected_waits=[3.5],
            expected_reason=ModelResponseEndReason.FIRST_EVENT_TIMEOUT,
            error_message="Timed out waiting for the first stream event.",
            notice="Timed out waiting for the model's initial response.",
        )

    async def test_idle_timeout_interrupts_pending_read_and_preserves_progress(self):
        await self._assert_pending_stream_timeout(
            timeout_config=RequestTimeoutConfig(10.0, 3.5, 30.0, 120.0),
            events=[
                TextDeltaEvent("partial answer"),
                UsageEvent(make_response("").usage),
            ],
            expected_waits=[3.5, 30.0, 30.0],
            expected_reason=ModelResponseEndReason.STREAM_IDLE_TIMEOUT,
            error_message="Timed out waiting for the next stream event.",
            notice=(
                "Timed out waiting for more data from the model. "
                "The answer may be incomplete."
            ),
        )

    async def test_total_deadline_interrupts_first_and_later_reads_and_displays_notice(
        self,
    ):
        for stage_seconds in (5.0, 30.0):
            for events in (
                [],
                [
                    TextDeltaEvent("partial answer"),
                    UsageEvent(make_response("").usage),
                ],
            ):
                with self.subTest(stage_seconds=stage_seconds, events=events):
                    await self._assert_pending_stream_timeout(
                        timeout_config=RequestTimeoutConfig(
                            10.0, stage_seconds, stage_seconds, 5.0
                        ),
                        events=events,
                        expected_waits=[5.0] * (len(events) + 1),
                        expected_reason=ModelResponseEndReason.REQUEST_DEADLINE_EXCEEDED,
                        error_message="The overall request deadline was exceeded.",
                        notice=(
                            "The overall request deadline was exceeded. "
                            "The answer may be incomplete."
                        ),
                    )

    async def test_stream_read_failure_keeps_partial_text_and_displays_notice(self):
        config = replace(self.config, stream_output_enabled=True)
        client = FakeClient(config)
        output = StringIO()
        closures = []

        async def failing_stream(request):
            try:
                yield TextDeltaEvent("partial answer")
                self.assertTrue(output.getvalue().endswith("partial answer"))
                raise RuntimeError("private upstream error details")
            finally:
                closures.append(True)

        with (
            patch(
                "llm_terminal_assistant.cli.PromptSession", autospec=True
            ) as prompt_session,
            patch(
                "llm_terminal_assistant.cli.create_default_tool_registry",
                return_value=self.registry,
            ),
            patch.object(client, "send_stream", side_effect=failing_stream) as send,
            redirect_stdout(output),
        ):
            configure_prompt_session(prompt_session, ["question", "exit"])
            await talk(client, config, self.budgeter)

        send.assert_called_once()
        self.assertEqual(closures, [True])
        self.assertEqual(
            output.getvalue(),
            "Please enter your prompt (type 'exit' to quit):\n\n"
            "Model Response: \npartial answer\n"
            "Streaming response could not be read. The answer may be incomplete.\n"
            "Exiting...\n",
        )

    def test_main_interleaves_logs_without_changing_response_or_history(self):
        config = replace(self.config, stream_output_enabled=True)
        client = FakeClient(config)
        output = StringIO()
        responses = []
        request_loops = []
        cleanup_loops = []
        cleanup_completed = []
        original_close = client.aclose
        root = logging.getLogger()

        async def logged_stream(request):
            close.assert_not_called()
            request_loops.append(asyncio.get_running_loop())
            client.requests.append(request)
            yield TextDeltaEvent("你好")
            logging.getLogger("llm_terminal_assistant.adapter.openai_client").warning(
                "example event"
            )
            yield TextDeltaEvent("继续")
            yield EndEvent(ModelResponseEndReason.COMPLETED_NORMALLY, None, None)

        async def observed_turn(*args, **kwargs):
            result = await send_stream_conversation_turn(*args, **kwargs)
            responses.append(result[0])
            return result

        async def observed_close():
            cleanup_loops.append(asyncio.get_running_loop())
            await asyncio.sleep(0)
            await original_close()
            cleanup_completed.append(True)

        with (
            patch.object(root, "handlers", []),
            patch.object(root, "level", logging.WARNING),
            patch("llm_terminal_assistant.cli.load_model_config", return_value=config),
            patch(
                "llm_terminal_assistant.cli.create_model_client", return_value=client
            ),
            patch(
                "llm_terminal_assistant.cli.create_budgeter", return_value=self.budgeter
            ),
            patch(
                "llm_terminal_assistant.cli.create_default_tool_registry",
                return_value=self.registry,
            ),
            patch(
                "llm_terminal_assistant.cli.PromptSession", autospec=True
            ) as prompt_session,
            patch(
                "llm_terminal_assistant.cli.send_stream_conversation_turn",
                side_effect=observed_turn,
            ),
            patch.object(client, "send_stream", side_effect=logged_stream),
            patch.object(client, "aclose", side_effect=observed_close) as close,
            redirect_stdout(output),
        ):
            configure_prompt_session(prompt_session, ["first", "second", "exit"])
            try:
                main()
            finally:
                for handler in root.handlers:
                    handler.close()

        self.assertEqual(len(request_loops), 2)
        self.assertIs(request_loops[0], request_loops[1])
        close.assert_awaited_once_with()
        self.assertEqual(cleanup_loops, [request_loops[0]])
        self.assertEqual(cleanup_completed, [True])
        self.assertTrue(request_loops[0].is_closed())
        self.assertEqual([response.text for response in responses], ["你好继续"] * 2)
        self.assertIn(Message("assistant", "你好继续"), client.requests[1].input)
        self.assertEqual(output.getvalue().count("[WARNING] example event"), 2)
        self.assertRegex(
            output.getvalue(), r"你好\n[^\n]*\[WARNING\] example event\n继续\n"
        )

    async def test_run_conversation_closes_client_when_model_request_raises(self):
        client = FakeClient(self.config)
        failure = RuntimeError("model request failed")
        with (
            patch(
                "llm_terminal_assistant.cli.PromptSession", autospec=True
            ) as prompt_session,
            patch.object(client, "send", side_effect=failure) as send,
            patch.object(client, "aclose", wraps=client.aclose) as close,
            redirect_stdout(StringIO()),
        ):
            configure_prompt_session(prompt_session, ["question"])
            with self.assertRaises(RuntimeError) as caught:
                await run_conversation(client, self.config, self.budgeter)

        send.assert_called_once()
        close.assert_awaited_once_with()
        self.assertIs(caught.exception, failure)

    async def test_disabled_streaming_keeps_full_response_output_and_tool_definitions(
        self,
    ):
        self.config = replace(self.config, stream_output_enabled=False)
        with patch.object(FakeClient, "send_stream") as send_stream:
            client, output = await self.run_talk(
                ["question"], [make_response("Full answer")]
            )

        send_stream.assert_not_called()
        self.assertEqual(client.requests[0].tools, self.registry.get_tool_list())
        self.assertEqual(
            output,
            "Please enter your prompt (type 'exit' to quit):\n\n"
            "Model Response: \nFull answer\nExiting...\n",
        )

    async def test_nonstream_cancel_keys_set_signal_and_wait_before_next_turn(self):
        for key_input in ("\x1b", "\x03"):
            with self.subTest(key_input=key_input):
                await self._assert_nonstream_worker_cleanup(key_input=key_input)

    async def test_nonstream_outer_cancellation_waits_for_worker_before_closing_client(
        self,
    ):
        for worker_failure in (None, RuntimeError("worker failed during cleanup")):
            with self.subTest(worker_failure=worker_failure):
                await self._assert_nonstream_worker_cleanup(
                    worker_failure=worker_failure
                )

    async def _assert_nonstream_worker_cleanup(
        self, *, key_input=None, worker_failure=None
    ):
        config = replace(self.config, stream_output_enabled=False)
        client = FakeClient(config)
        loop = asyncio.get_running_loop()
        loop_thread = get_ident()
        started, signal_seen, finished = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )
        release_worker = Event()
        cancel_events, lifecycle = [], []
        output = StringIO()

        class ObservedCancelEvent(Event):
            def __init__(self):
                super().__init__()
                cancel_events.append(self)

            def set(self):
                super().set()
                loop.call_soon_threadsafe(signal_seen.set)

        def blocking_send(request):
            self.assertNotEqual(get_ident(), loop_thread)
            client.requests.append(request)
            if len(client.requests) > 1:
                self.assertEqual(lifecycle, ["worker finished"])
                return make_response("next answer")
            loop.call_soon_threadsafe(started.set)
            try:
                # The gate controls completion; the timeout only bounds test failures.
                if not release_worker.wait(5):
                    raise AssertionError("The test did not release the worker")
                if worker_failure is not None:
                    raise worker_failure
                return make_response("first answer")
            finally:
                lifecycle.append("worker finished")
                loop.call_soon_threadsafe(finished.set)

        async def close_client():
            self.assertEqual(lifecycle, ["worker finished"])
            lifecycle.append("client closed")

        with (
            create_pipe_input() as terminal_input,
            patch("llm_terminal_assistant.cli.PromptSession") as session,
            patch("llm_terminal_assistant.cli.Event", ObservedCancelEvent),
            patch(
                "llm_terminal_assistant.cli.send_conversation_turn",
                wraps=send_conversation_turn,
            ) as send_turn,
            patch.object(client, "send", side_effect=blocking_send),
            patch.object(client, "aclose", side_effect=close_client) as close,
            redirect_stdout(output),
        ):
            prompt = AsyncMock(side_effect=["first", "second", "exit"])
            session.return_value = SimpleNamespace(
                app=SimpleNamespace(input=terminal_input, ttimeoutlen=0),
                prompt_async=prompt,
            )
            task = asyncio.create_task(run_conversation(client, config, self.budgeter))
            try:
                async with asyncio.timeout(2):
                    await started.wait()
                    if key_input is None:
                        task.cancel()
                    else:
                        terminal_input.send_text(key_input)
                    await signal_seen.wait()
                    await asyncio.sleep(0)
                    self.assertTrue(cancel_events[0].is_set())
                    self.assertFalse(task.done())
                    self.assertEqual(task.cancelling(), int(key_input is None))
                    self.assertEqual(prompt.await_count, 1)
                    self.assertEqual(lifecycle, [])
                    close.assert_not_awaited()
                    release_worker.set()
                    if key_input is None:
                        with self.assertRaises(asyncio.CancelledError):
                            await task
                    else:
                        await task
            finally:
                release_worker.set()
                if not task.done() and not task.cancelling():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                if started.is_set():
                    await asyncio.wait_for(finished.wait(), timeout=2)

        self.assertEqual(lifecycle, ["worker finished", "client closed"])
        close.assert_awaited_once_with()
        expected_turns = 1 if key_input is None else 2
        self.assertEqual(len(client.requests), expected_turns)
        self.assertEqual(len(cancel_events), expected_turns)
        self.assertEqual(send_turn.call_count, expected_turns)
        for call, event in zip(send_turn.call_args_list, cancel_events, strict=True):
            self.assertIs(call.kwargs["cancel_event"], event)
        if key_input is not None:
            self.assertIsNot(cancel_events[0], cancel_events[1])
            self.assertFalse(cancel_events[1].is_set())
            self.assertEqual(output.getvalue().count("Request was cancelled."), 1)
            self.assertNotIn("first answer", output.getvalue())
            self.assertIn("next answer\nExiting...", output.getvalue())

    async def test_bracketed_multiline_paste_is_sent_once_and_exit_still_works(self):
        for trailing_newline in ("", "\n"):
            with self.subTest(trailing_newline=bool(trailing_newline)):
                self.encoder.reset_mock()
                text = f"请按顺序完成以下步骤\n\n1. 查询时间。\n2. 根据结果继续。{trailing_newline}"
                client = FakeClient(
                    self.config, scripted_responses=[make_response("Done")]
                )
                output = StringIO()
                with (
                    create_pipe_input() as terminal_input,
                    create_app_session(input=terminal_input, output=DummyOutput()),
                    patch(
                        "llm_terminal_assistant.cli.create_default_tool_registry",
                        return_value=self.registry,
                    ),
                    redirect_stdout(output),
                ):
                    terminal_input.send_text(f"\x1b[200~{text}\x1b[201~\rexit\r")
                    await talk(client, self.config, self.budgeter)

                self.assertEqual(len(client.requests), 1)
                self.assertEqual(
                    client.requests[0].input,
                    [
                        Message("system", "You are a helpful assistant."),
                        Message("user", text),
                    ],
                )
                self.assertIn("Done", output.getvalue())
                self.assertIn("Exiting...", output.getvalue())

    async def test_exit_with_surrounding_whitespace_does_not_send_a_request(self):
        client, output = await self.run_talk([" \nEXIT\n "], [])

        self.assertEqual(client.requests, [])
        self.assertIn("Exiting...", output)

    async def test_plain_answers_reuse_registry_without_executing_tools(self):
        client, output = await self.run_talk(
            ["Hello", "Another question"],
            [make_response("First answer"), make_response("Second answer")],
        )

        self.assertEqual(len(client.requests), 2)
        self.clock.assert_not_called()
        self.assertIn("First answer", output)
        self.assertIn("Second answer", output)
        self.assertEqual(
            client.requests[1].input,
            [
                Message("system", "You are a helpful assistant."),
                Message("user", "Hello"),
                Message("assistant", "First answer"),
                Message("user", "Another question"),
            ],
        )

    async def test_tool_loop_stop_shows_reason_and_allows_next_question(self):
        for reason in (
            ToolLoopStopReason.MAX_TOOL_ROUNDS_REACHED,
            ToolLoopStopReason.MAX_MODEL_REQUESTS_REACHED,
            ToolLoopStopReason.MAX_TOOL_EXECUTIONS_REACHED,
        ):
            with self.subTest(reason=reason):
                self.encoder.reset_mock()
                with (
                    patch(
                        "llm_terminal_assistant.cli.send_conversation_turn",
                        side_effect=[ToolLoopStoppedError(reason), DEFAULT],
                        wraps=send_conversation_turn,
                    ) as send_turn,
                    self.assertLogs(
                        "llm_terminal_assistant.cli", level="ERROR"
                    ) as logs,
                ):
                    client, output = await self.run_talk(
                        ["Stopped question", "Next question"],
                        [make_response("Next answer")],
                    )

                self.assertIn(
                    f"Tool loop stopped due to: {reason.value}", logs.output[0]
                )
                self.assertEqual(send_turn.call_count, 2)
                self.assertEqual(len(client.requests), 1)
                self.assertIn("Next answer", output)
                self.assertEqual(
                    client.requests[0].input,
                    [
                        Message("system", "You are a helpful assistant."),
                        Message("user", "Next question"),
                    ],
                )

    async def test_cancellation_stops_tools_and_followup_requests_from_talk(self):
        cases = (
            ("model response", 2, 0),
            ("first tool", 2, 1),
            ("last tool", 1, 1),
        )
        for stop_after, tool_count, expected_executions in cases:
            with self.subTest(stop_after=stop_after):
                await self._assert_cancelled_tool_flow(
                    stop_after, tool_count, expected_executions
                )

    async def _assert_cancelled_tool_flow(
        self, stop_after, tool_count, expected_executions
    ):
        config = replace(self.config, stream_output_enabled=False)
        cancel_event = Event()
        calls = [
            ToolCallRequest(f"time-{index}", "get_current_time", '{"timezone":"UTC"}')
            for index in range(tool_count)
        ]
        tool_response = make_response("Checking the time.", calls)
        client = FakeClient(
            config,
            scripted_responses=[tool_response, make_response("Unexpected follow-up")],
        )
        original_send = client.send
        stop_reasons = []
        output = StringIO()

        def send_and_maybe_cancel(request):
            response = original_send(request)
            if stop_after == "model response":
                cancel_event.set()
            return response

        def cancel_after_tool():
            cancel_event.set()
            return self.clock.return_value

        clock = Mock(side_effect=cancel_after_tool)
        registry = create_default_tool_registry(clock=clock)

        def observed_turn(*args, **kwargs):
            self.assertIs(kwargs["cancel_event"], cancel_event)
            try:
                return send_conversation_turn(*args, **kwargs)
            except ToolLoopStoppedError as error:
                stop_reasons.append(error.reason)
                raise

        with (
            patch("llm_terminal_assistant.cli.PromptSession", autospec=True) as session,
            patch("llm_terminal_assistant.cli.Event", return_value=cancel_event),
            patch(
                "llm_terminal_assistant.cli.create_default_tool_registry",
                return_value=registry,
            ),
            patch(
                "llm_terminal_assistant.cli.send_conversation_turn",
                side_effect=observed_turn,
            ),
            patch.object(client, "send", side_effect=send_and_maybe_cancel),
            self.assertNoLogs("llm_terminal_assistant.cli", level="ERROR"),
            redirect_stdout(output),
        ):
            configure_prompt_session(session, ["question", "exit"])
            await talk(client, config, self.budgeter)

        self.assertTrue(cancel_event.is_set())
        self.assertEqual(stop_reasons, [ToolLoopStopReason.REQUEST_CANCELLED])
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(client.requests[0].tools, registry.get_tool_list())
        self.assertEqual(clock.call_count, expected_executions)
        self.assertEqual(session.return_value.prompt_async.await_count, 2)
        self.assertEqual(output.getvalue().count("Request was cancelled."), 1)
        self.assertNotIn("Checking the time.", output.getvalue())
        self.assertNotIn("Unexpected follow-up", output.getvalue())
        self.assertIn("Exiting...", output.getvalue())

    async def test_time_tool_history_is_replayed_and_only_final_answers_are_displayed(
        self,
    ):
        tool_call = ToolCallRequest(
            call_id="time-call-1",
            name="get_current_time",
            arguments='{"timezone":"Asia/Shanghai"}',
        )
        with self.assertLogs("llm_terminal_assistant", level="INFO") as logs:
            client, output = await self.run_talk(
                ["What time is it in Shanghai?", "Did you use a tool?"],
                [
                    make_response("Checking the clock.", [tool_call]),
                    make_response("Shanghai time is 12:00."),
                    make_response("Yes, I used the clock tool."),
                ],
            )

        self.assertEqual(len(client.requests), 3)
        self.clock.assert_called_once_with()
        second_input = client.requests[1].input
        self.assertEqual(
            second_input[:-1],
            [
                *client.requests[0].input,
                Message("assistant", "Checking the clock."),
                tool_call,
            ],
        )
        result = second_input[-1]
        self.assertIsInstance(result, ToolCallResult)
        self.assertEqual(result.call_id, tool_call.call_id)
        self.assertEqual(
            json.loads(result.output),
            {
                "timezone": "Asia/Shanghai",
                "current_time": "2026-10-04T12:00:00+08:00",
            },
        )
        self.assertIn("Shanghai time is 12:00.", output)
        self.assertIn("Yes, I used the clock tool.", output)
        self.assertNotIn("Checking the clock.", output)
        self.assertNotIn(tool_call.call_id, output)
        self.assertEqual(
            client.requests[0].input,
            [
                Message("system", "You are a helpful assistant."),
                Message("user", "What time is it in Shanghai?"),
            ],
        )
        self.assertEqual(
            client.requests[2].input,
            [
                *second_input,
                Message("assistant", "Shanghai time is 12:00."),
                Message("user", "Did you use a tool?"),
            ],
        )
        log_text = "\n".join(logs.output)
        self.assertNotIn(tool_call.arguments, log_text)
        self.assertNotIn(result.output, log_text)
        self.assertIn("tool_call_count=1 tool_result_count=1", log_text)

    async def test_talk_trims_whole_tool_turns_and_saves_current_turn_after_trimming(
        self,
    ):
        system_message = Message("system", "You are a helpful assistant.")
        tool_call = ToolCallRequest(
            "time-call-1", "get_current_time", '{"timezone":"Asia/Shanghai"}'
        )
        tool_turn = [
            Message("user", "What time is it?"),
            Message("assistant", "Checking the clock."),
            tool_call,
            ToolCallResult(
                tool_call.call_id,
                json.dumps(
                    {
                        "timezone": "Asia/Shanghai",
                        "current_time": "2026-10-04T12:00:00+08:00",
                    }
                ),
            ),
            Message("assistant", "Shanghai time is 12:00."),
        ]
        recent_turn = [
            Message("user", "Recent question"),
            Message("assistant", "r" * 1_000),
        ]
        current_user = Message("user", "q" * 1_200)
        current_answer = Message("assistant", "Current answer")
        next_user = Message("user", "Next question")
        for retain_tool_turn in (True, False):
            with self.subTest(retain_tool_turn=retain_tool_turn):
                self.clock.reset_mock()
                self.encoder.reset_mock()
                retained_history = (
                    [*tool_turn, *recent_turn] if retain_tool_turn else recent_turn
                )
                expected_current_input = [
                    system_message,
                    *retained_history,
                    current_user,
                ]
                expected_request = ModelRequest(
                    input=expected_current_input,
                    reserved_output_tokens=self.config.default_reserved_output_tokens,
                    tools=self.registry.get_tool_list(),
                )
                expected_encoded = FakeModelRequestEncoder().encode_request(
                    expected_request
                )
                counter = Mock(wraps=CodePointTokenCounter())
                self.budgeter = Budgeter(
                    token_counter=counter,
                    request_encoder=self.encoder,
                    model_limits=ModelLimits(
                        context_window_tokens=len(expected_encoded)
                        + self.config.default_reserved_output_tokens
                    ),
                    safety_margin_tokens=0,
                )
                prompts = [
                    tool_turn[0].content,
                    recent_turn[0].content,
                    current_user.content,
                    next_user.content,
                ]
                responses = [
                    make_response("Checking the clock.", [tool_call]),
                    make_response(tool_turn[-1].content),
                    make_response(recent_turn[-1].content),
                    make_response(current_answer.content),
                    make_response("Next answer"),
                ]
                if retain_tool_turn:
                    prompts.insert(0, "Old question")
                    responses.insert(0, make_response("Old answer"))
                expected_requests = len(responses)

                client, output = await self.run_talk(
                    prompts,
                    responses,
                    expected_budget_checks=expected_requests + 2,
                )

                self.assertEqual(len(client.requests), expected_requests)
                self.clock.assert_called_once_with()
                self.assertEqual(client.requests[-2].input, expected_current_input)
                self.assertEqual(
                    counter.count_tokens.call_args_list[-3].args[0],
                    expected_encoded,
                )
                self.assertEqual(
                    client.requests[-1].input,
                    [
                        system_message,
                        *(recent_turn if retain_tool_turn else []),
                        current_user,
                        current_answer,
                        next_user,
                    ],
                )
                self.assertIn("Current answer", output)
                self.assertIn("Next answer", output)
                self.assertNotIn("Checking the clock.", output)

    async def test_tool_round_limit_does_not_display_or_save_unfinished_turn(self):
        self.config = replace(
            self.config,
            tool_loop_limits=ToolLoopLimits(max_tool_rounds=1, max_model_requests=5),
        )
        first_call = ToolCallRequest(
            "time-call-1", "get_current_time", '{"timezone":"Asia/Shanghai"}'
        )
        pending_call = replace(first_call, call_id="time-call-2")
        with self.assertLogs("llm_terminal_assistant.cli", level="ERROR") as logs:
            client, output = await self.run_talk(
                ["Earlier question", "Unfinished question", "Next question"],
                [
                    make_response("Earlier answer"),
                    make_response("Checking the clock.", [first_call]),
                    make_response("More checking is needed.", [pending_call]),
                    make_response("Next answer"),
                ],
            )

        self.assertEqual(len(client.requests), 4)
        self.clock.assert_called_once_with()
        self.assertIn(
            "Tool loop stopped due to: max_tool_rounds_reached",
            logs.output[0],
        )
        self.assertNotIn("Checking the clock.", output)
        self.assertNotIn("More checking is needed.", output)
        self.assertIn("Next answer", output)
        self.assertEqual(
            client.requests[-1].input,
            [
                Message("system", "You are a helpful assistant."),
                Message("user", "Earlier question"),
                Message("assistant", "Earlier answer"),
                Message("user", "Next question"),
            ],
        )

    async def test_execution_budget_resets_after_completed_or_stopped_turn(self):
        self.config = replace(
            self.config,
            tool_loop_limits=ToolLoopLimits(
                max_tool_rounds=5,
                max_model_requests=6,
                max_tool_executions=1,
            ),
        )
        first_call = ToolCallRequest(
            "time-call-1", "get_current_time", '{"timezone":"Asia/Shanghai"}'
        )
        pending_call = replace(first_call, call_id="pending-call")
        next_call = replace(first_call, call_id="time-call-2")
        for stopped in (False, True):
            with self.subTest(stopped=stopped):
                self.clock.reset_mock()
                self.encoder.reset_mock()
                first_calls = [first_call, pending_call] if stopped else [first_call]
                responses = [make_response("First check.", first_calls)]
                if not stopped:
                    responses.append(make_response("First answer"))
                responses.extend(
                    [
                        make_response("Next check.", [next_call]),
                        make_response("Next answer"),
                    ]
                )

                with self.assertLogs(
                    "llm_terminal_assistant.cli", level="INFO"
                ) as logs:
                    client, output = await self.run_talk(
                        ["First question", "Next question"], responses
                    )

                self.assertEqual(len(client.requests), 3 if stopped else 4)
                self.assertEqual(self.clock.call_count, 2)
                self.assertIn("Next answer", output)
                self.assertNotIn("First check.", output)
                self.assertNotIn("Next check.", output)
                stop_logs = [
                    message for message in logs.output if "Tool loop stopped" in message
                ]
                if stopped:
                    self.assertEqual(len(stop_logs), 1)
                    self.assertIn("max_tool_executions_reached", stop_logs[0])
                    self.assertNotIn("First answer", output)
                else:
                    self.assertEqual(stop_logs, [])
                    self.assertIn("First answer", output)
                result = client.requests[-1].input[-1]
                self.assertIsInstance(result, ToolCallResult)
                self.assertEqual(result.call_id, next_call.call_id)

    async def test_noncompleted_responses_with_calls_show_status_and_keep_text_in_history(
        self,
    ):
        tool_call = ToolCallRequest(
            "time-call-1", "get_current_time", '{"timezone":"Asia/Shanghai"}'
        )
        outcomes = [
            (
                ModelResponseEndReason.REQUEST_FAILED,
                ModelResponseError("test_error", "Request failed."),
                None,
                "Request was failed: [test_error] Request failed.",
            ),
            (
                ModelResponseEndReason.REQUEST_CANCELLED,
                None,
                None,
                "Request was cancelled.",
            ),
            (
                ModelResponseEndReason.REQUEST_INCOMPLETE,
                None,
                ModelResponseIncompleteDetails("max_output_tokens"),
                "Request was incomplete: max_output_tokens",
            ),
        ]
        for reason, error, details, notice in outcomes:
            for after_tool in (False, True):
                with self.subTest(reason=reason, after_tool=after_tool):
                    self.clock.reset_mock()
                    self.encoder.reset_mock()
                    response = replace(
                        make_response(
                            "Nonfinal response text",
                            [replace(tool_call, call_id="pending-call")],
                        ),
                        reason=reason,
                        error=error,
                        incomplete_details=details,
                    )
                    responses = [response, make_response("Next answer")]
                    if after_tool:
                        responses.insert(
                            0, make_response("Checking the clock.", [tool_call])
                        )
                    client, output = await self.run_talk(
                        ["Interrupted question", "Next question"], responses
                    )

                    self.assertEqual(len(client.requests), 3 if after_tool else 2)
                    self.assertEqual(self.clock.call_count, 1 if after_tool else 0)
                    self.assertIn(notice, output)
                    self.assertNotIn("Additional tool calls remain pending.", output)
                    self.assertNotIn(response.text, output)
                    history_items = client.requests[-2].input[1:]
                    self.assertEqual(
                        client.requests[-1].input,
                        [
                            Message("system", "You are a helpful assistant."),
                            *history_items,
                            Message("assistant", response.text),
                            Message("user", "Next question"),
                        ],
                    )


if __name__ == "__main__":
    unittest.main()

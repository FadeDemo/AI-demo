import json
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import UTC, datetime
from io import StringIO
from unittest.mock import DEFAULT, Mock, patch

from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from llm_terminal_assistant.adapter.fake_client import FakeClient
from llm_terminal_assistant.adapter.fake_model import (
    CodePointTokenCounter,
    FakeModelRequestEncoder,
)
from llm_terminal_assistant.budgeter import Budgeter
from llm_terminal_assistant.cli import send_conversation_turn, talk
from llm_terminal_assistant.config import ModelConfig
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


class TalkTests(unittest.TestCase):
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

    def run_talk(
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
                "llm_terminal_assistant.cli.prompt",
                side_effect=[*prompts, "exit"],
            ),
            patch(
                "llm_terminal_assistant.cli.create_default_tool_registry",
                return_value=self.registry,
            ) as create_registry,
            redirect_stdout(output),
        ):
            talk(client, self.config, self.budgeter)

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

    def test_bracketed_multiline_paste_is_sent_once_and_exit_still_works(self):
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
                    talk(client, self.config, self.budgeter)

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

    def test_exit_with_surrounding_whitespace_does_not_send_a_request(self):
        client, output = self.run_talk([" \nEXIT\n "], [])

        self.assertEqual(client.requests, [])
        self.assertIn("Exiting...", output)

    def test_plain_answers_reuse_registry_without_executing_tools(self):
        client, output = self.run_talk(
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

    def test_tool_loop_stop_shows_reason_and_allows_next_question(self):
        for reason in ToolLoopStopReason:
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
                    client, output = self.run_talk(
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

    def test_time_tool_history_is_replayed_and_only_final_answers_are_displayed(self):
        tool_call = ToolCallRequest(
            call_id="time-call-1",
            name="get_current_time",
            arguments='{"timezone":"Asia/Shanghai"}',
        )
        with self.assertLogs("llm_terminal_assistant", level="INFO") as logs:
            client, output = self.run_talk(
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

    def test_talk_trims_whole_tool_turns_and_saves_current_turn_after_trimming(self):
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

                client, output = self.run_talk(
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

    def test_tool_round_limit_does_not_display_or_save_unfinished_turn(self):
        self.config = replace(
            self.config,
            tool_loop_limits=ToolLoopLimits(max_tool_rounds=1, max_model_requests=5),
        )
        first_call = ToolCallRequest(
            "time-call-1", "get_current_time", '{"timezone":"Asia/Shanghai"}'
        )
        pending_call = replace(first_call, call_id="time-call-2")
        with self.assertLogs("llm_terminal_assistant.cli", level="ERROR") as logs:
            client, output = self.run_talk(
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

    def test_execution_budget_resets_after_completed_or_stopped_turn(self):
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
                    client, output = self.run_talk(
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

    def test_noncompleted_responses_with_calls_show_status_and_keep_text_in_history(
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
                    client, output = self.run_talk(
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

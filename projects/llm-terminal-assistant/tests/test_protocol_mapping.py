import unittest
from copy import deepcopy

from llm_terminal_assistant.adapter.protocol_mapping import to_deepseek_messages
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import ModelRequest
from llm_terminal_assistant.tools.definition import ToolDefinition
from llm_terminal_assistant.tools.protocol import ToolCallRequest, ToolCallResult


class DeepSeekMessageMappingTests(unittest.TestCase):
    def test_messages_without_tools_keep_their_order_and_content(self):
        request = ModelRequest(
            input=[
                Message("user", "question"),
                Message("system", "instruction"),
                Message("assistant", "answer"),
            ],
            reserved_output_tokens=20,
        )

        self.assertEqual(
            to_deepseek_messages(request),
            [
                {"role": "user", "content": "question"},
                {"role": "system", "content": "instruction"},
                {"role": "assistant", "content": "answer"},
            ],
        )

    def test_tools_attach_once_to_first_system_with_complete_schemas(self):
        schemas = [
            {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "minLength": 1,
                    }
                },
                "required": ["timezone"],
                "additionalProperties": False,
            },
            {"type": "object", "properties": {}, "additionalProperties": False},
        ]
        request = ModelRequest(
            input=[Message("system", "first"), Message("system", "second")],
            reserved_output_tokens=20,
            tools=[
                ToolDefinition("clock", "Read clock", schemas[0]),
                ToolDefinition("calendar", "Read calendar", schemas[1]),
            ],
        )
        original = deepcopy(request)

        self.assertEqual(
            to_deepseek_messages(request),
            [
                {
                    "role": "system",
                    "content": "first",
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "clock",
                                "description": "Read clock",
                                "parameters": schemas[0],
                            },
                        },
                        {
                            "type": "function",
                            "function": {
                                "name": "calendar",
                                "description": "Read calendar",
                                "parameters": schemas[1],
                            },
                        },
                    ],
                },
                {"role": "system", "content": "second"},
            ],
        )
        self.assertEqual(request, original)

    def test_tools_prepend_empty_system_without_losing_first_message(self):
        request = ModelRequest(
            input=[Message("user", "question"), Message("system", "later")],
            reserved_output_tokens=20,
            tools=[ToolDefinition("clock", "Read clock", {"type": "object"})],
        )

        messages = to_deepseek_messages(request)

        self.assertEqual(
            messages[0],
            {
                "role": "system",
                "content": "",
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "clock",
                            "description": "Read clock",
                            "parameters": {"type": "object"},
                        },
                    }
                ],
            },
        )
        self.assertEqual(
            messages[1:],
            [
                {"role": "user", "content": "question"},
                {"role": "system", "content": "later"},
            ],
        )

    def test_call_prefers_preceding_assistant_and_preserves_following_text(self):
        request = ModelRequest(
            input=[
                Message("assistant", "before"),
                ToolCallRequest("call-1", "clock", '{"timezone":"UTC"}'),
                Message("assistant", "after"),
            ],
            reserved_output_tokens=20,
        )

        self.assertEqual(
            to_deepseek_messages(request),
            [
                {
                    "role": "assistant",
                    "content": "before",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "clock",
                                "arguments": '{"timezone":"UTC"}',
                            },
                        }
                    ],
                },
                {"role": "assistant", "content": "after"},
            ],
        )

    def test_call_consumes_immediately_following_assistant_once(self):
        request = ModelRequest(
            input=[
                Message("user", "question"),
                ToolCallRequest("call-1", "clock", "{}"),
                Message("assistant", "checking"),
                ToolCallResult("call-1", "12:00"),
            ],
            reserved_output_tokens=20,
        )
        original = deepcopy(request)

        self.assertEqual(
            to_deepseek_messages(request),
            [
                {"role": "user", "content": "question"},
                {
                    "role": "assistant",
                    "content": "checking",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "clock", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call-1", "content": "12:00"},
            ],
        )
        self.assertEqual(request, original)

    def test_call_does_not_merge_across_non_assistant_items(self):
        barriers = [
            Message("user", "barrier"),
            Message("system", "barrier"),
            ToolCallResult("previous-call", "barrier"),
        ]
        expected_barriers = [
            {"role": "user", "content": "barrier"},
            {"role": "system", "content": "barrier"},
            {"role": "tool", "tool_call_id": "previous-call", "content": "barrier"},
        ]
        for barrier, expected_barrier in zip(barriers, expected_barriers, strict=True):
            with self.subTest(barrier=barrier):
                request = ModelRequest(
                    input=[
                        Message("assistant", "before"),
                        barrier,
                        ToolCallRequest("call-1", "clock", "{}"),
                        barrier,
                        Message("assistant", "after"),
                    ],
                    reserved_output_tokens=20,
                )

                self.assertEqual(
                    to_deepseek_messages(request),
                    [
                        {"role": "assistant", "content": "before"},
                        expected_barrier,
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {"name": "clock", "arguments": "{}"},
                                }
                            ],
                        },
                        expected_barrier,
                        {"role": "assistant", "content": "after"},
                    ],
                )

    def test_consecutive_calls_share_assistant_in_input_order(self):
        request = ModelRequest(
            input=[
                ToolCallRequest("call-1", "clock", "{}"),
                ToolCallRequest("call-2", "calendar", "{}"),
                ToolCallResult("call-1", "12:00"),
                ToolCallResult("call-2", "Monday"),
            ],
            reserved_output_tokens=20,
        )

        self.assertEqual(
            to_deepseek_messages(request),
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "clock",
                                "arguments": "{}",
                            },
                        },
                        {
                            "id": "call-2",
                            "type": "function",
                            "function": {
                                "name": "calendar",
                                "arguments": "{}",
                            },
                        },
                    ],
                },
                {"role": "tool", "tool_call_id": "call-1", "content": "12:00"},
                {"role": "tool", "tool_call_id": "call-2", "content": "Monday"},
            ],
        )

    def test_empty_input_mapping_returns_empty_list(self):
        for tools in ([], [ToolDefinition("clock", "Read clock", {"type": "object"})]):
            with self.subTest(tools=tools):
                request = ModelRequest(input=[], reserved_output_tokens=20, tools=tools)
                self.assertEqual(to_deepseek_messages(request), [])


if __name__ == "__main__":
    unittest.main()

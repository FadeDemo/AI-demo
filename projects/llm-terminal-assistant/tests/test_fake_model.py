import json
import unittest

from llm_terminal_assistant.adapter.fake_model import (
    CodePointTokenCounter,
    FakeModelRequestEncoder,
)
from llm_terminal_assistant.budgeter import (
    Budgeter,
    BudgetRejectedError,
    BudgetRejectionReason,
)
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import ModelLimits, ModelRequest
from llm_terminal_assistant.tools.definition import ToolDefinition
from llm_terminal_assistant.tools.protocol import ToolCallRequest, ToolCallResult


class FakeModelRequestEncoderTests(unittest.TestCase):
    def test_encodes_plain_messages_without_tools(self):
        request = ModelRequest(
            input=[
                Message(role="system", content="Helpful assistant"),
                Message(role="user", content="现在几点"),
            ],
            reserved_output_tokens=20,
            reasoning_effort="none",
        )

        encoded = FakeModelRequestEncoder().encode_request(request)

        self.assertEqual(
            json.loads(encoded),
            {
                "input": [
                    {"role": "system", "content": "Helpful assistant"},
                    {"role": "user", "content": "现在几点"},
                ],
                "reasoning_effort": "none",
                "tools": [],
            },
        )
        self.assertIn("现在几点", encoded)

    def test_encodes_mixed_input_once_in_original_order(self):
        request = ModelRequest(
            input=[
                Message(role="user", content="USER_SENTINEL"),
                ToolCallRequest(
                    call_id="call-1",
                    name="get_current_time",
                    arguments='{"timezone":"Asia/Shanghai"}',
                ),
                ToolCallResult(
                    call_id="call-1",
                    output='{"time":"RESULT_SENTINEL"}',
                ),
            ],
            reserved_output_tokens=20,
        )

        encoded = FakeModelRequestEncoder().encode_request(request)

        self.assertEqual(
            json.loads(encoded)["input"],
            [
                {"role": "user", "content": "USER_SENTINEL"},
                {
                    "type": "function_call",
                    "call_id": "call-1",
                    "name": "get_current_time",
                    "arguments": '{"timezone":"Asia/Shanghai"}',
                },
                {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": '{"time":"RESULT_SENTINEL"}',
                },
            ],
        )
        self.assertEqual(encoded.count("USER_SENTINEL"), 1)
        self.assertEqual(encoded.count("get_current_time"), 1)
        self.assertEqual(encoded.count("RESULT_SENTINEL"), 1)

    def test_encodes_all_tool_definitions_and_complete_parameter_schemas(self):
        request = ModelRequest(
            input=[Message(role="user", content="What time is it?")],
            reserved_output_tokens=20,
            tools=[
                ToolDefinition(
                    name="get_current_time",
                    description="TIME_DESCRIPTION_SENTINEL",
                    parameter_schema={
                        "type": "object",
                        "properties": {
                            "timezone": {"type": "string", "minLength": 1},
                        },
                        "required": ["timezone"],
                        "additionalProperties": False,
                    },
                ),
                ToolDefinition(
                    name="fake_tool",
                    description="FAKE_DESCRIPTION_SENTINEL",
                    parameter_schema={"type": "object", "properties": {}},
                ),
            ],
        )

        encoded = FakeModelRequestEncoder().encode_request(request)

        self.assertEqual(
            json.loads(encoded)["tools"],
            [
                {
                    "name": "get_current_time",
                    "description": "TIME_DESCRIPTION_SENTINEL",
                    "parameter_schema": {
                        "type": "object",
                        "properties": {
                            "timezone": {"type": "string", "minLength": 1},
                        },
                        "required": ["timezone"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "fake_tool",
                    "description": "FAKE_DESCRIPTION_SENTINEL",
                    "parameter_schema": {"type": "object", "properties": {}},
                },
            ],
        )
        self.assertEqual(encoded.count("TIME_DESCRIPTION_SENTINEL"), 1)
        self.assertEqual(encoded.count("FAKE_DESCRIPTION_SENTINEL"), 1)

    def test_tool_payloads_can_exceed_fake_input_budget(self):
        encoder = FakeModelRequestEncoder()
        counter = CodePointTokenCounter()
        base_request = ModelRequest(
            input=[Message(role="user", content="What time is it?")],
            reserved_output_tokens=20,
        )
        base_token_count = counter.count_tokens(encoder.encode_request(base_request))
        budgeter = Budgeter(
            token_counter=counter,
            request_encoder=encoder,
            model_limits=ModelLimits(
                context_window_tokens=100_000,
                max_input_tokens=base_token_count,
            ),
            safety_margin_tokens=0,
        )

        self.assertEqual(
            budgeter.check(base_request).estimated_input_tokens, base_token_count
        )

        requests = {
            "tool definition": ModelRequest(
                input=list(base_request.input),
                reserved_output_tokens=20,
                tools=[
                    ToolDefinition(
                        name="get_current_time",
                        description="Get the current time",
                        parameter_schema={"type": "object"},
                    ),
                ],
            ),
            "tool request": ModelRequest(
                input=[
                    *base_request.input,
                    ToolCallRequest(
                        call_id="call-1", name="get_current_time", arguments="{}"
                    ),
                ],
                reserved_output_tokens=20,
            ),
            "tool request and result": ModelRequest(
                input=[
                    *base_request.input,
                    ToolCallRequest(
                        call_id="call-1", name="get_current_time", arguments="{}"
                    ),
                    ToolCallResult(call_id="call-1", output='{"time":"12:00"}'),
                ],
                reserved_output_tokens=20,
            ),
        }
        for name, request in requests.items():
            with self.subTest(payload=name):
                with self.assertRaises(BudgetRejectedError) as caught:
                    budgeter.check(request)
                self.assertEqual(
                    caught.exception.reason, BudgetRejectionReason.MAX_INPUT_EXCEEDED
                )


if __name__ == "__main__":
    unittest.main()

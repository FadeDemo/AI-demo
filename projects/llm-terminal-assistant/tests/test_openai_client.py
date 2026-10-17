import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from llm_terminal_assistant.adapter.openai_client import OpenAIClient
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import (
    DEEPSEEK_V4_FLASH,
    DEEPSEEK_V41_FLASH,
    DEEPSEEK_V41_FLASH_1017,
    ModelOutputFormat,
    ModelRequest,
    ModelResponseEndReason,
    ModelResponseError,
    ModelResponseIncompleteDetails,
)
from llm_terminal_assistant.stream.events import EndEvent, TextDeltaEvent, UsageEvent
from llm_terminal_assistant.tools.definition import ToolDefinition
from llm_terminal_assistant.tools.protocol import ToolCallRequest, ToolCallResult


class RecordingStream:
    def __init__(self, events):
        self.events = events
        self.closed = False

    def __iter__(self):
        return iter(self.events)

    def close(self):
        self.closed = True


class RecordingResponses:
    def __init__(self):
        self.create_kwargs = None

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        response = SimpleNamespace(
            model=kwargs["model"],
            output_text="response",
            status="completed",
            usage=SimpleNamespace(
                input_tokens=1,
                input_tokens_details=SimpleNamespace(
                    cached_tokens=0,
                    cache_write_tokens=0,
                ),
                output_tokens=1,
                output_tokens_details=SimpleNamespace(reasoning_tokens=0),
                total_tokens=2,
            ),
            output=[],
        )
        if kwargs.get("stream"):
            self.stream = RecordingStream(
                [
                    SimpleNamespace(type="response.output_text.delta", delta=delta)
                    for delta in ("first", "", "third")
                ]
                + [SimpleNamespace(type="response.completed", response=response)]
            )
            return self.stream
        return response


class OpenAIClientTests(unittest.TestCase):
    def test_ultra_is_allowed_only_by_1017_profile_and_sent_unchanged(self):
        client = OpenAIClient.__new__(OpenAIClient)
        client.model = "deepseek-flash"
        responses = RecordingResponses()
        client.client = SimpleNamespace(responses=responses)

        for profile in (DEEPSEEK_V4_FLASH, DEEPSEEK_V41_FLASH):
            with (
                self.subTest(profile=profile.profile_id),
                self.assertRaisesRegex(ValueError, "not supported"),
            ):
                client.validate_reasoning_effort(
                    "ultra", profile.allowed_reasoning_efforts
                )

        client.validate_reasoning_effort(
            "ultra", DEEPSEEK_V41_FLASH_1017.allowed_reasoning_efforts
        )
        client.send(
            ModelRequest(
                input=[Message("user", "question")],
                reserved_output_tokens=20,
                reasoning_effort="ultra",
            )
        )
        self.assertEqual(responses.create_kwargs["reasoning"], {"effort": "ultra"})

    def test_streaming_preserves_request_options_without_affecting_later_send(self):
        requests = [
            ModelRequest(
                input=[Message(role="user", content="question")],
                reserved_output_tokens=321,
            ),
            ModelRequest(
                input=[
                    Message(role="user", content="question"),
                    ToolCallRequest(call_id="call-1", name="lookup", arguments="{}"),
                    ToolCallResult(call_id="call-1", output="result"),
                ],
                reserved_output_tokens=321,
                reasoning_effort="none",
                temperature=0.0,
                top_p=0.8,
                output_format=ModelOutputFormat(
                    type="json_schema",
                    name="answer",
                    schema={"type": "object"},
                ),
                tools=[
                    ToolDefinition(
                        name="lookup",
                        description="Looks up a value.",
                        parameter_schema={"type": "object"},
                    )
                ],
            ),
        ]
        for request in requests:
            with self.subTest(request=request):
                responses = RecordingResponses()
                client = object.__new__(OpenAIClient)
                client.model = "test-model"
                client.client = SimpleNamespace(responses=responses)

                client.send(request)
                expected_options = responses.create_kwargs.copy()
                list(client.send_stream(request))

                self.assertEqual(
                    responses.create_kwargs, {**expected_options, "stream": True}
                )
                client.send(request)
                self.assertEqual(responses.create_kwargs, expected_options)
                self.assertNotIn("stream", responses.create_kwargs)

    def test_streams_text_then_usage_and_end_and_closes_sdk_stream(self):
        responses = RecordingResponses()
        client = object.__new__(OpenAIClient)
        client.model = "test-model"
        client.client = SimpleNamespace(responses=responses)
        request = ModelRequest(
            input=[Message(role="user", content="question")],
            reserved_output_tokens=321,
        )

        expected_response = client.send(request)
        events = client.send_stream(request)
        for delta in ("first", "", "third"):
            self.assertEqual(next(events), TextDeltaEvent(delta=delta))
        self.assertEqual(next(events), UsageEvent(usage=expected_response.usage))
        self.assertEqual(
            next(events),
            EndEvent(
                reason=expected_response.reason,
                error=expected_response.error,
                incomplete_details=expected_response.incomplete_details,
            ),
        )
        with self.assertRaises(StopIteration):
            next(events)
        self.assertTrue(responses.stream.closed)

    def test_maps_output_truncation_without_usage_and_closes_sdk_stream(self):
        stream = RecordingStream(
            [
                SimpleNamespace(type="response.output_text.delta", delta="partial"),
                SimpleNamespace(
                    type="response.incomplete",
                    response=SimpleNamespace(
                        status="incomplete",
                        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
                        usage=None,
                    ),
                ),
            ]
        )
        client = object.__new__(OpenAIClient)
        client.model = "test-model"
        client.client = SimpleNamespace(
            responses=SimpleNamespace(create=Mock(return_value=stream))
        )
        request = ModelRequest(
            input=[Message(role="user", content="question")],
            reserved_output_tokens=321,
        )

        events = client.send_stream(request)

        self.assertEqual(next(events), TextDeltaEvent(delta="partial"))
        self.assertEqual(
            next(events),
            EndEvent(
                reason=ModelResponseEndReason.REQUEST_INCOMPLETE,
                error=None,
                incomplete_details=ModelResponseIncompleteDetails(
                    reason="max_output_tokens"
                ),
            ),
        )
        with self.assertRaises(StopIteration):
            next(events)
        self.assertTrue(stream.closed)

    def test_maps_failed_response_error_and_closes_sdk_stream(self):
        stream = RecordingStream(
            [
                SimpleNamespace(type="response.output_text.delta", delta="partial"),
                SimpleNamespace(
                    type="response.failed",
                    response=SimpleNamespace(
                        status="failed",
                        error=SimpleNamespace(
                            code="server_error",
                            message="Generation failed.",
                        ),
                        usage=None,
                    ),
                ),
            ]
        )
        client = object.__new__(OpenAIClient)
        client.model = "test-model"
        client.client = SimpleNamespace(
            responses=SimpleNamespace(create=Mock(return_value=stream))
        )
        request = ModelRequest(
            input=[Message(role="user", content="question")],
            reserved_output_tokens=321,
        )

        events = client.send_stream(request)

        self.assertEqual(next(events), TextDeltaEvent(delta="partial"))
        self.assertEqual(
            next(events),
            EndEvent(
                reason=ModelResponseEndReason.REQUEST_FAILED,
                error=ModelResponseError(
                    code="server_error",
                    message="Generation failed.",
                ),
                incomplete_details=None,
            ),
        )
        with self.assertRaises(StopIteration):
            next(events)
        self.assertTrue(stream.closed)

    def test_closes_sdk_stream_when_reading_or_conversion_raises(self):
        def failing_events():
            yield SimpleNamespace(type="response.output_text.delta", delta="partial")
            raise RuntimeError("stream read failed")

        cases = [
            (failing_events(), RuntimeError, "stream read failed"),
            (
                [SimpleNamespace(type="response.output_text.delta")],
                AttributeError,
                "delta",
            ),
        ]
        for raw_events, error_type, message in cases:
            with self.subTest(error_type=error_type):
                stream = RecordingStream(raw_events)
                client = object.__new__(OpenAIClient)
                client.model = "test-model"
                client.client = SimpleNamespace(
                    responses=SimpleNamespace(create=Mock(return_value=stream))
                )
                request = ModelRequest(
                    input=[Message(role="user", content="question")],
                    reserved_output_tokens=321,
                )

                with self.assertRaisesRegex(error_type, message):
                    list(client.send_stream(request))

                self.assertTrue(stream.closed)

    def test_maps_input_items_to_responses_input_in_order(self):
        responses = RecordingResponses()
        client = object.__new__(OpenAIClient)
        client.model = "test-model"
        client.client = SimpleNamespace(responses=responses)
        request = ModelRequest(
            input=[
                Message(role="user", content="What time is it?"),
                ToolCallRequest(
                    call_id="call-1",
                    name="get_current_time",
                    arguments='{"timezone":"Asia/Shanghai"}',
                ),
                ToolCallResult(
                    call_id="call-1",
                    output='{"time":"12:00"}',
                ),
            ],
            reserved_output_tokens=321,
        )

        client.send(request)

        self.assertEqual(
            responses.create_kwargs["input"],
            [
                {"role": "user", "content": "What time is it?"},
                {
                    "type": "function_call",
                    "call_id": "call-1",
                    "name": "get_current_time",
                    "arguments": '{"timezone":"Asia/Shanghai"}',
                },
                {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": '{"time":"12:00"}',
                },
            ],
        )

    def test_maps_reserved_output_tokens_to_responses_output_limit(self):
        responses = RecordingResponses()
        client = object.__new__(OpenAIClient)
        client.model = "test-model"
        client.client = SimpleNamespace(responses=responses)
        request = ModelRequest(
            input=[Message(role="user", content="question")],
            reserved_output_tokens=321,
        )

        client.send(request)

        self.assertEqual(responses.create_kwargs["max_output_tokens"], 321)

    def test_sends_none_reasoning_effort(self):
        responses = RecordingResponses()
        client = object.__new__(OpenAIClient)
        client.model = "test-model"
        client.client = SimpleNamespace(responses=responses)
        request = ModelRequest(
            input=[Message(role="user", content="question")],
            reserved_output_tokens=321,
            reasoning_effort="none",
        )

        client.send(request)

        self.assertEqual(
            responses.create_kwargs["reasoning"],
            {"effort": "none"},
        )

    def test_omits_reasoning_when_effort_is_none(self):
        responses = RecordingResponses()
        client = object.__new__(OpenAIClient)
        client.model = "test-model"
        client.client = SimpleNamespace(responses=responses)
        request = ModelRequest(
            input=[Message(role="user", content="question")],
            reserved_output_tokens=321,
            reasoning_effort=None,
        )

        client.send(request)

        self.assertNotIn("reasoning", responses.create_kwargs)

    def test_maps_temperature_to_responses_request(self):
        responses = RecordingResponses()
        client = object.__new__(OpenAIClient)
        client.model = "test-model"
        client.client = SimpleNamespace(responses=responses)
        request = ModelRequest(
            input=[Message(role="user", content="question")],
            reserved_output_tokens=321,
            temperature=0.4,
        )

        client.send(request)

        self.assertEqual(responses.create_kwargs["temperature"], 0.4)

    def test_maps_top_p_to_responses_request(self):
        responses = RecordingResponses()
        client = object.__new__(OpenAIClient)
        client.model = "test-model"
        client.client = SimpleNamespace(responses=responses)
        request = ModelRequest(
            input=[Message(role="user", content="question")],
            reserved_output_tokens=321,
            top_p=0.8,
        )

        client.send(request)

        self.assertEqual(responses.create_kwargs["top_p"], 0.8)

    def test_omits_sampling_parameters_when_none(self):
        responses = RecordingResponses()
        client = object.__new__(OpenAIClient)
        client.model = "test-model"
        client.client = SimpleNamespace(responses=responses)
        request = ModelRequest(
            input=[Message(role="user", content="question")],
            reserved_output_tokens=321,
            temperature=None,
            top_p=None,
        )

        client.send(request)

        self.assertNotIn("temperature", responses.create_kwargs)
        self.assertNotIn("top_p", responses.create_kwargs)

    def test_maps_json_schema_output_format_to_responses_text_format(self):
        responses = RecordingResponses()
        client = object.__new__(OpenAIClient)
        client.model = "test-model"
        client.client = SimpleNamespace(responses=responses)
        schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
            },
            "required": ["answer"],
            "additionalProperties": False,
        }
        request = ModelRequest(
            input=[Message(role="user", content="question")],
            reserved_output_tokens=321,
            output_format=ModelOutputFormat(
                type="json_schema",
                name="answer",
                schema=schema,
            ),
        )

        client.send(request)

        self.assertEqual(
            responses.create_kwargs["text"],
            {
                "format": {
                    "type": "json_schema",
                    "name": "answer",
                    "schema": schema,
                }
            },
        )

    def test_omits_text_configuration_when_output_format_is_none(self):
        responses = RecordingResponses()
        client = object.__new__(OpenAIClient)
        client.model = "test-model"
        client.client = SimpleNamespace(responses=responses)
        request = ModelRequest(
            input=[Message(role="user", content="question")],
            reserved_output_tokens=321,
        )

        client.send(request)

        self.assertNotIn("text", responses.create_kwargs)

    def test_maps_tool_definitions_to_responses_tools(self):
        responses = RecordingResponses()
        client = object.__new__(OpenAIClient)
        client.model = "test-model"
        client.client = SimpleNamespace(responses=responses)
        parameter_schema = {
            "type": "object",
            "properties": {
                "timezone": {"type": "string"},
            },
            "required": ["timezone"],
            "additionalProperties": False,
        }
        request = ModelRequest(
            input=[Message(role="user", content="question")],
            reserved_output_tokens=321,
            tools=[
                ToolDefinition(
                    name="get_current_time",
                    description="Returns the current time.",
                    parameter_schema=parameter_schema,
                )
            ],
        )

        client.send(request)

        self.assertEqual(
            responses.create_kwargs["tools"],
            [
                {
                    "type": "function",
                    "name": "get_current_time",
                    "description": "Returns the current time.",
                    "parameters": parameter_schema,
                }
            ],
        )

    def test_omits_tools_when_request_has_no_tool_definitions(self):
        responses = RecordingResponses()
        client = object.__new__(OpenAIClient)
        client.model = "test-model"
        client.client = SimpleNamespace(responses=responses)
        request = ModelRequest(
            input=[Message(role="user", content="question")],
            reserved_output_tokens=321,
        )

        client.send(request)

        self.assertNotIn("tools", responses.create_kwargs)


if __name__ == "__main__":
    unittest.main()

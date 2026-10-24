import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from llm_terminal_assistant.adapter.openai_client import OpenAIClient
from llm_terminal_assistant.config import ModelConfig, RequestTimeoutConfig
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
from llm_terminal_assistant.stream.consumer import consume_stream
from llm_terminal_assistant.stream.events import EndEvent, TextDeltaEvent, UsageEvent
from llm_terminal_assistant.tools.definition import ToolDefinition
from llm_terminal_assistant.tools.protocol import ToolCallRequest, ToolCallResult


class RecordingStream:
    def __init__(self, events):
        self.events = events
        self.closed = False
        self.read_count = 0

    async def __aiter__(self):
        for event in self.events:
            self.read_count += 1
            yield event

    async def close(self):
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


class RecordingAsyncResponses(RecordingResponses):
    async def create(self, **kwargs):
        return super().create(**kwargs)


class OpenAIClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_status_errors_map_to_terminal_events(self):
        from httpx import Request, Response
        from openai import (
            AuthenticationError,
            BadRequestError,
            InternalServerError,
            PermissionDeniedError,
            RateLimitError,
            UnprocessableEntityError,
        )

        for status, error_type, expected_reason in (
            (429, RateLimitError, ModelResponseEndReason.RATE_LIMITED),
            (503, InternalServerError, ModelResponseEndReason.SERVICE_UNAVAILABLE),
            (401, AuthenticationError, ModelResponseEndReason.AUTHENTICATION_FAILED),
            (403, PermissionDeniedError, ModelResponseEndReason.PERMISSION_DENIED),
            (400, BadRequestError, ModelResponseEndReason.INVALID_REQUEST),
            (422, UnprocessableEntityError, ModelResponseEndReason.INVALID_REQUEST),
        ):
            with self.subTest(status=status):
                error = error_type(
                    "Service request failed.",
                    response=Response(
                        status, request=Request("POST", "https://example.invalid")
                    ),
                    body=None,
                )
                create = AsyncMock(side_effect=error)
                client = object.__new__(OpenAIClient)
                client.model = "test-model"
                client.stream_client = SimpleNamespace(
                    responses=SimpleNamespace(create=create)
                )

                events = [
                    event
                    async for event in client.send_stream(
                        ModelRequest(input=[], reserved_output_tokens=20)
                    )
                ]

                self.assertEqual(
                    events,
                    [
                        EndEvent(
                            expected_reason,
                            ModelResponseError(expected_reason, error.message),
                            None,
                        )
                    ],
                )
                create.assert_awaited_once()

    async def test_connection_timeout_during_creation_reaches_consumer_as_end_reason(
        self,
    ):
        from httpx import ConnectTimeout, Request
        from openai import APITimeoutError

        error = APITimeoutError(request=Request("POST", "https://example.invalid"))
        error.__cause__ = ConnectTimeout("connection timed out")
        client = object.__new__(OpenAIClient)
        client.model = "deepseek-flash"
        client.stream_client = SimpleNamespace(
            responses=SimpleNamespace(create=AsyncMock(side_effect=error))
        )
        consumer = Mock()

        response = await consume_stream(
            client.send_stream(ModelRequest(input=[], reserved_output_tokens=20)),
            consumer,
            start_at=0.0,
            clock=lambda: 1.0,
        )

        self.assertEqual(response.reason, ModelResponseEndReason.CONNECTION_TIMEOUT)
        self.assertEqual(response.error.code, ModelResponseEndReason.CONNECTION_TIMEOUT)
        self.assertEqual(response.error.message, error.message)
        self.assertEqual(response.text, "")
        consumer.assert_not_called()
        client.stream_client.responses.create.assert_awaited_once()

    async def test_other_creation_errors_propagate_without_cleanup_masking_them(self):
        from httpx import Request, Response, WriteTimeout
        from openai import (
            APITimeoutError,
            InternalServerError,
            NotFoundError,
        )

        request = Request("POST", "https://example.invalid")
        write_error = APITimeoutError(request=request)
        write_error.__cause__ = WriteTimeout("write timed out")
        for error in (
            write_error,
            APITimeoutError(request=request),
            RuntimeError("creation failed"),
            *(
                error_type(
                    "Service request failed.",
                    response=Response(status, request=request),
                    body=None,
                )
                for status, error_type in (
                    (404, NotFoundError),
                    (500, InternalServerError),
                    (502, InternalServerError),
                )
            ),
        ):
            with self.subTest(error=error):
                client = object.__new__(OpenAIClient)
                client.model = "deepseek-flash"
                client.stream_client = SimpleNamespace(
                    responses=SimpleNamespace(create=AsyncMock(side_effect=error))
                )

                with self.assertRaises(type(error)) as caught:
                    await anext(
                        client.send_stream(
                            ModelRequest(input=[], reserved_output_tokens=20)
                        )
                    )

                self.assertIs(caught.exception, error)
                client.stream_client.responses.create.assert_awaited_once()

    async def test_clients_are_created_on_first_use_and_reused_without_timeout_override(
        self,
    ):
        config = ModelConfig(
            api_key="test-key",
            base_url="https://example.invalid",
            model="deepseek-flash",
            model_profile=DEEPSEEK_V41_FLASH_1017,
            provider="openai",
        )

        request = ModelRequest(input=[], reserved_output_tokens=20)
        for streaming in (False, True):
            with (
                self.subTest(streaming=streaming),
                patch("openai.OpenAI") as sync_constructor,
                patch("openai.AsyncOpenAI") as async_constructor,
            ):
                sync_constructor.return_value.responses = RecordingResponses()
                async_constructor.return_value.responses = RecordingAsyncResponses()
                client = OpenAIClient(config)
                sync_constructor.assert_not_called()
                async_constructor.assert_not_called()
                self.assertIsNone(client.client)
                self.assertIsNone(client.stream_client)

                for _ in range(2):
                    if streaming:
                        events = [event async for event in client.send_stream(request)]
                        self.assertIsInstance(events[-1], EndEvent)
                    else:
                        self.assertEqual(client.send(request).text, "response")

                if streaming:
                    used, unused = async_constructor, sync_constructor
                    self.assertIs(client.stream_client, used.return_value)
                    self.assertIsNone(client.client)
                else:
                    used, unused = sync_constructor, async_constructor
                    self.assertIs(client.client, used.return_value)
                    self.assertIsNone(client.stream_client)
                used.assert_called_once_with(
                    api_key=config.api_key, base_url=config.base_url
                )
                unused.assert_not_called()

    async def test_aclose_closes_only_created_clients(self):
        config = ModelConfig(
            api_key="test-key",
            base_url="https://example.invalid",
            model="deepseek-flash",
            model_profile=DEEPSEEK_V41_FLASH_1017,
            provider="openai",
        )
        request = ModelRequest(input=[], reserved_output_tokens=20)
        for use_sync, use_async in (
            (False, False),
            (True, False),
            (False, True),
            (True, True),
        ):
            sync_client = SimpleNamespace(
                responses=RecordingResponses(), close=Mock(return_value=None)
            )
            async_client = SimpleNamespace(
                responses=RecordingAsyncResponses(), close=AsyncMock(return_value=None)
            )
            with (
                self.subTest(use_sync=use_sync, use_async=use_async),
                patch("openai.OpenAI", return_value=sync_client) as sync_constructor,
                patch(
                    "openai.AsyncOpenAI", return_value=async_client
                ) as async_constructor,
            ):
                client = OpenAIClient(config)
                if use_sync:
                    client.send(request)
                if use_async:
                    events = [event async for event in client.send_stream(request)]
                    self.assertIsInstance(events[-1], EndEvent)
                    self.assertTrue(async_client.responses.stream.closed)

                sync_client.close.assert_not_called()
                async_client.close.assert_not_called()

                await client.aclose()

                self.assertEqual(sync_constructor.call_count, int(use_sync))
                self.assertEqual(async_constructor.call_count, int(use_async))
                if use_sync:
                    sync_client.close.assert_called_once_with()
                else:
                    sync_client.close.assert_not_called()
                if use_async:
                    async_client.close.assert_awaited_once_with()
                else:
                    async_client.close.assert_not_called()

    async def test_timeout_config_overrides_only_connect_without_mutating_sdk_defaults(
        self,
    ):
        from openai import DEFAULT_TIMEOUT

        original_defaults = DEFAULT_TIMEOUT.as_dict()
        config = ModelConfig(
            api_key="test-key",
            base_url="https://example.invalid",
            model="deepseek-flash",
            model_profile=DEEPSEEK_V41_FLASH_1017,
            provider="openai",
            request_timeout_config=RequestTimeoutConfig(0.25, 2.0, 3.0, 4.0),
        )

        with (
            patch("openai.OpenAI") as sync_constructor,
            patch("openai.AsyncOpenAI") as async_constructor,
        ):
            sync_constructor.return_value.responses = RecordingResponses()
            async_constructor.return_value.responses = RecordingAsyncResponses()
            client = OpenAIClient(config)
            request = ModelRequest(input=[], reserved_output_tokens=20)
            client.send(request)
            events = [event async for event in client.send_stream(request)]
            self.assertIsInstance(events[-1], EndEvent)

        for constructor in (sync_constructor, async_constructor):
            constructor.assert_called_once()
            timeout = constructor.call_args.kwargs["timeout"]
            self.assertIsNot(timeout, DEFAULT_TIMEOUT)
            self.assertEqual(timeout.as_dict(), {**original_defaults, "connect": 0.25})
        self.assertEqual(DEFAULT_TIMEOUT.as_dict(), original_defaults)

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

    async def test_streaming_preserves_request_options_without_affecting_later_send(
        self,
    ):
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
                stream_responses = RecordingAsyncResponses()
                client = object.__new__(OpenAIClient)
                client.model = "test-model"
                client.client = SimpleNamespace(responses=responses)
                client.stream_client = SimpleNamespace(responses=stream_responses)

                client.send(request)
                expected_options = responses.create_kwargs.copy()
                events = [event async for event in client.send_stream(request)]

                self.assertIsInstance(events[-1], EndEvent)
                self.assertEqual(
                    stream_responses.create_kwargs, {**expected_options, "stream": True}
                )
                client.send(request)
                self.assertEqual(responses.create_kwargs, expected_options)
                self.assertNotIn("stream", responses.create_kwargs)

    async def test_streams_text_then_usage_and_end_and_closes_sdk_stream(self):
        responses = RecordingResponses()
        stream_responses = RecordingAsyncResponses()
        client = object.__new__(OpenAIClient)
        client.model = "test-model"
        client.client = SimpleNamespace(responses=responses)
        client.stream_client = SimpleNamespace(responses=stream_responses)
        request = ModelRequest(
            input=[Message(role="user", content="question")],
            reserved_output_tokens=321,
        )

        expected_response = client.send(request)
        events = client.send_stream(request)
        for delta in ("first", "", "third"):
            self.assertEqual(await anext(events), TextDeltaEvent(delta=delta))
        self.assertEqual(await anext(events), UsageEvent(usage=expected_response.usage))
        self.assertEqual(
            await anext(events),
            EndEvent(
                reason=expected_response.reason,
                error=expected_response.error,
                incomplete_details=expected_response.incomplete_details,
            ),
        )
        with self.assertRaises(StopAsyncIteration):
            await anext(events)
        self.assertTrue(stream_responses.stream.closed)

    async def test_maps_output_truncation_without_usage_and_closes_sdk_stream(self):
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
        client.stream_client = SimpleNamespace(
            responses=SimpleNamespace(create=AsyncMock(return_value=stream))
        )
        request = ModelRequest(
            input=[Message(role="user", content="question")],
            reserved_output_tokens=321,
        )

        events = client.send_stream(request)

        self.assertEqual(await anext(events), TextDeltaEvent(delta="partial"))
        self.assertEqual(
            await anext(events),
            EndEvent(
                reason=ModelResponseEndReason.REQUEST_INCOMPLETE,
                error=None,
                incomplete_details=ModelResponseIncompleteDetails(
                    reason="max_output_tokens"
                ),
            ),
        )
        with self.assertRaises(StopAsyncIteration):
            await anext(events)
        self.assertTrue(stream.closed)

    async def test_maps_failed_response_error_and_closes_sdk_stream(self):
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
        client.stream_client = SimpleNamespace(
            responses=SimpleNamespace(create=AsyncMock(return_value=stream))
        )
        request = ModelRequest(
            input=[Message(role="user", content="question")],
            reserved_output_tokens=321,
        )

        events = client.send_stream(request)

        self.assertEqual(await anext(events), TextDeltaEvent(delta="partial"))
        self.assertEqual(
            await anext(events),
            EndEvent(
                reason=ModelResponseEndReason.REQUEST_FAILED,
                error=ModelResponseError(
                    code="server_error",
                    message="Generation failed.",
                ),
                incomplete_details=None,
            ),
        )
        with self.assertRaises(StopAsyncIteration):
            await anext(events)
        self.assertTrue(stream.closed)

    async def test_closes_sdk_stream_when_reading_or_conversion_raises(self):
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
                client.stream_client = SimpleNamespace(
                    responses=SimpleNamespace(create=AsyncMock(return_value=stream))
                )
                request = ModelRequest(
                    input=[Message(role="user", content="question")],
                    reserved_output_tokens=321,
                )

                with self.assertRaisesRegex(error_type, message):
                    async for _ in client.send_stream(request):
                        pass

                self.assertTrue(stream.closed)

    async def test_closing_generator_early_awaits_sdk_cleanup_without_reading_more(
        self,
    ):
        stream = RecordingStream(
            [
                SimpleNamespace(type="response.output_text.delta", delta="first"),
                SimpleNamespace(type="response.output_text.delta", delta="unread"),
            ]
        )
        client = object.__new__(OpenAIClient)
        client.model = "test-model"
        client.stream_client = SimpleNamespace(
            responses=SimpleNamespace(create=AsyncMock(return_value=stream))
        )
        events = client.send_stream(ModelRequest(input=[], reserved_output_tokens=20))

        self.assertEqual(await anext(events), TextDeltaEvent("first"))
        self.assertFalse(stream.closed)
        await events.aclose()

        self.assertTrue(stream.closed)
        self.assertEqual(stream.read_count, 1)
        with self.assertRaises(StopAsyncIteration):
            await anext(events)

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

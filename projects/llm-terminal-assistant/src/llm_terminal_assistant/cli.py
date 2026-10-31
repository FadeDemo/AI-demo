import asyncio
import logging
import random
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from threading import Event
from time import monotonic

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding.key_processor import KeyPress
from prompt_toolkit.keys import Keys

from llm_terminal_assistant.budgeter import (
    Budgeter,
    BudgetRejectedError,
    BudgetRejectionReason,
)
from llm_terminal_assistant.budgeter_factory import create_budgeter
from llm_terminal_assistant.client import ModelClient
from llm_terminal_assistant.client_factory import create_model_client
from llm_terminal_assistant.config import (
    ModelConfig,
    RequestRetryConfig,
    RequestTimeoutConfig,
    load_model_config,
)
from llm_terminal_assistant.conversation import (
    ConversationTurn,
    HistoryTrimResult,
    build_tool_followup_request,
    trim_history,
)
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import (
    ModelInputItem,
    ModelRequest,
    ModelResponse,
    ModelResponseEndReason,
    ModelResponseError,
)
from llm_terminal_assistant.observability import observe_request
from llm_terminal_assistant.request_control import (
    RequestStoppedError,
    RequestStopReason,
    check_request_cancelled,
    check_request_deadline,
)
from llm_terminal_assistant.request_retry import (
    calculate_retry_delay,
    can_retry_response,
    wait_before_retry,
)
from llm_terminal_assistant.stream.consumer import consume_stream
from llm_terminal_assistant.stream.timing import StreamResponseTiming
from llm_terminal_assistant.terminal_output import TerminalLogHandler, TerminalOutput
from llm_terminal_assistant.tools.definition import ToolDefinition
from llm_terminal_assistant.tools.errors import ToolLoopStoppedError, ToolLoopStopReason
from llm_terminal_assistant.tools.executor import ToolExecutor
from llm_terminal_assistant.tools.factory import create_default_tool_registry
from llm_terminal_assistant.tools.loop import (
    ToolExecutionBudget,
    ToolLoopLimits,
)
from llm_terminal_assistant.tools.protocol import ToolCallRequest, ToolCallResult
from llm_terminal_assistant.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

terminal_output = TerminalOutput()

DEFAULT_TOOL_LOOP_LIMITS = ToolLoopLimits()


def output_request_cancelled() -> None:
    terminal_output.write_line("Request was cancelled.")


def output_response_status(response: ModelResponse) -> None:
    if response.reason == ModelResponseEndReason.COMPLETED_NORMALLY:
        pass
    elif response.reason == ModelResponseEndReason.REQUEST_FAILED:
        terminal_output.write_line(
            f"Request was failed: [{response.error.code}] {response.error.message}"
        )
    elif response.reason == ModelResponseEndReason.REQUEST_CANCELLED:
        output_request_cancelled()
    elif response.reason == ModelResponseEndReason.REQUEST_INCOMPLETE:
        terminal_output.write_line(
            f"Request was incomplete: {response.incomplete_details.reason}"
        )
    elif response.reason == ModelResponseEndReason.MISSING_END_EVENT:
        terminal_output.write_line(
            "Streaming response ended without a terminal event. "
            "The answer may be incomplete."
        )
    elif response.reason == ModelResponseEndReason.STREAM_READ_FAILED:
        terminal_output.write_line(
            "Streaming response could not be read. The answer may be incomplete."
        )
    elif response.reason == ModelResponseEndReason.CONNECTION_TIMEOUT:
        terminal_output.write_line(
            "Connection timed out. Could not connect to the model service."
        )
    elif response.reason == ModelResponseEndReason.FIRST_EVENT_TIMEOUT:
        terminal_output.write_line(
            "Timed out waiting for the model's initial response."
        )
    elif response.reason == ModelResponseEndReason.STREAM_IDLE_TIMEOUT:
        terminal_output.write_line(
            "Timed out waiting for more data from the model. The answer may be incomplete."
        )
    elif response.reason == ModelResponseEndReason.REQUEST_DEADLINE_EXCEEDED:
        terminal_output.write_line(
            "The overall request deadline was exceeded. The answer may be incomplete."
        )
    elif response.reason == ModelResponseEndReason.RATE_LIMITED:
        terminal_output.write_line("Rate limited. Please try again later.")
    elif response.reason == ModelResponseEndReason.SERVICE_UNAVAILABLE:
        terminal_output.write_line("Service unavailable. Please try again later.")
    elif response.reason == ModelResponseEndReason.AUTHENTICATION_FAILED:
        terminal_output.write_line(
            "Authentication failed. Please check your credentials."
        )
    elif response.reason == ModelResponseEndReason.PERMISSION_DENIED:
        terminal_output.write_line("Permission denied. Please check your permissions.")
    elif response.reason == ModelResponseEndReason.INVALID_REQUEST:
        terminal_output.write_line("Invalid request. Please check your request.")
    elif response.reason == ModelResponseEndReason.CONNECTION_FAILED:
        terminal_output.write_line("Connection failed. Please check your connection.")
    elif response.reason == ModelResponseEndReason.READ_TIMEOUT:
        terminal_output.write_line(
            "Timed out while reading from the model service. "
            "The answer may be incomplete."
        )
    elif response.reason == ModelResponseEndReason.INSUFFICIENT_RETRY_TIME:
        terminal_output.write_line(
            "Insufficient retry time. The request was not retried."
        )


def output_model_response(response: ModelResponse):
    terminal_output.write_line("Model Response: ")
    if response.reason == ModelResponseEndReason.COMPLETED_NORMALLY:
        terminal_output.write_line(response.text)
    output_response_status(response)


def model_response_to_assistant_message(response: ModelResponse) -> Message:
    return Message(role="assistant", content=response.text)


def log_model_request_summary(request: ModelRequest, request_id: str) -> None:
    logger.info(
        "ModelRequest[%s]: input_item_count=%d message_count=%d tool_call_count=%d tool_result_count=%d tool_definition_count=%d",
        request_id,
        len(request.input),
        sum(isinstance(item, Message) for item in request.input),
        sum(isinstance(item, ToolCallRequest) for item in request.input),
        sum(isinstance(item, ToolCallResult) for item in request.input),
        len(request.tools),
    )


def _prepare_conversation_request(
    system_message: Message,
    history: list[ConversationTurn],
    turn_input: list[ModelInputItem],
    reserved_output_tokens: int,
    min_reserved_recent_turns: int,
    budgeter: Budgeter,
    reasoning_effort: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    tools: list[ToolDefinition] | None = None,
    *,
    request_id: str,
) -> HistoryTrimResult:
    trim_result = trim_history(
        system_message=system_message,
        completed_turns=history,
        current_turn_input=turn_input,
        reserved_output_tokens=reserved_output_tokens,
        reasoning_effort=reasoning_effort,
        min_reserved_recent_turns=min_reserved_recent_turns,
        budgeter=budgeter,
        temperature=temperature,
        top_p=top_p,
        tools=tools,
    )
    budget_result = trim_result.budget_result
    logger.info(
        "ModelRequest[%s]: Budget check passed: estimated_input_tokens=%d reserved_output_tokens=%d safety_margin_tokens=%d remaining_tokens=%d",
        request_id,
        budget_result.estimated_input_tokens,
        budget_result.reserved_output_tokens,
        budget_result.safety_margin_tokens,
        budget_result.remaining_tokens,
    )
    log_model_request_summary(trim_result.request, request_id)
    return trim_result


def send_conversation_turn(
    client: ModelClient,
    budgeter: Budgeter,
    system_message: Message,
    completed_turns: list[ConversationTurn],
    current_user_message: Message,
    reserved_output_tokens: int,
    min_reserved_recent_turns: int,
    reasoning_effort: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    tools: list[ToolDefinition] | None = None,
    executor: ToolExecutor | None = None,
    tool_loop_limits: ToolLoopLimits = DEFAULT_TOOL_LOOP_LIMITS,
    *,
    cancel_event: Event | None = None,
    clock: Callable[[], float] = monotonic,
    request_timeout_config: RequestTimeoutConfig | None = None,
) -> tuple[ModelResponse, HistoryTrimResult]:
    with observe_request(
        logger,
        entry="tools",
        model=client.model,
        system_prompt=system_message.content,
        clock=clock,
    ) as observation:
        start_at = observation.start_at
        deadline_at = (
            start_at + request_timeout_config.request_deadline_seconds
            if request_timeout_config is not None
            else None
        )
        request_id = observation.request_id

        def trim_and_send(
            turn_input: list[ModelInputItem],
            history: list[ConversationTurn],
        ) -> tuple[ModelResponse, HistoryTrimResult]:
            trim_result = _prepare_conversation_request(
                system_message,
                history,
                turn_input,
                reserved_output_tokens,
                min_reserved_recent_turns,
                budgeter,
                reasoning_effort,
                temperature,
                top_p,
                tools,
                request_id=request_id,
            )
            check_request_cancelled(cancel_event)
            check_request_deadline(deadline_at=deadline_at, clock=clock)
            observation.begin_model_call()
            try:
                response = client.send(trim_result.request)
            except Exception:
                observation.reason = "model_call_failed"
                observation.log_model_call(logger, None)
                raise
            observation.log_model_call(logger, response)
            check_request_cancelled(cancel_event)
            check_request_deadline(deadline_at=deadline_at, clock=clock)
            return response, trim_result

        current_turn_input = [current_user_message]
        model_response, trim_result = trim_and_send(current_turn_input, completed_turns)
        if (
            model_response.reason != ModelResponseEndReason.COMPLETED_NORMALLY
            or not model_response.tool_calls
        ):
            observation.reason = model_response.reason
            return model_response, trim_result
        if executor is None:
            raise ValueError("Tool calls were made, but no executor was provided.")

        tool_rounds, model_requests = 0, 1
        tool_execution_budget = ToolExecutionBudget(
            max_tool_executions=tool_loop_limits.max_tool_executions
        )
        while (
            model_response.reason == ModelResponseEndReason.COMPLETED_NORMALLY
            and model_response.tool_calls
        ):
            if tool_rounds >= tool_loop_limits.max_tool_rounds:
                raise ToolLoopStoppedError(
                    reason=ToolLoopStopReason.MAX_TOOL_ROUNDS_REACHED
                )
            if model_requests >= tool_loop_limits.max_model_requests:
                raise ToolLoopStoppedError(
                    reason=ToolLoopStopReason.MAX_MODEL_REQUESTS_REACHED
                )
            model_request = trim_result.request
            followup_request = build_tool_followup_request(
                request=model_request,
                response=model_response,
                executor=executor,
                tool_execution_budget=tool_execution_budget,
                cancel_event=cancel_event,
                clock=clock,
                deadline_at=deadline_at,
                request_id=request_id,
            )
            current_turn_start = len(model_request.input) - len(current_turn_input)
            current_turn_input = followup_request.input[current_turn_start:]
            model_response, trim_result = trim_and_send(
                current_turn_input,
                trim_result.retained_completed_turns,
            )
            tool_rounds += 1
            model_requests += 1
        observation.reason = model_response.reason
        return model_response, trim_result


async def send_stream_conversation_turn(
    client: ModelClient,
    budgeter: Budgeter,
    system_message: Message,
    completed_turns: list[ConversationTurn],
    current_user_message: Message,
    reserved_output_tokens: int,
    min_reserved_recent_turns: int,
    reasoning_effort: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    *,
    display_text: Callable[[str], None],
    clock: Callable[[], float] = monotonic,
    request_timeout_config: RequestTimeoutConfig | None = None,
    request_retry_config: RequestRetryConfig,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    uniform: Callable[[float, float], float] = random.uniform,
) -> tuple[ModelResponse, HistoryTrimResult]:
    with observe_request(
        logger,
        entry="stream",
        model=client.model,
        system_prompt=system_message.content,
        clock=clock,
    ) as observation:
        start_at = observation.start_at
        request_id = observation.request_id
        deadline_at = (
            start_at + request_timeout_config.request_deadline_seconds
            if request_timeout_config is not None
            else None
        )
        trim_result = _prepare_conversation_request(
            system_message,
            completed_turns,
            [current_user_message],
            reserved_output_tokens,
            min_reserved_recent_turns,
            budgeter,
            reasoning_effort,
            temperature,
            top_p,
            request_id=request_id,
        )
        model_response: ModelResponse | None = None
        try:
            while True:
                task = asyncio.current_task()
                if task is not None and task.cancelling() > 0:
                    raise asyncio.CancelledError()
                check_request_deadline(deadline_at=deadline_at, clock=clock)
                attempt = observation.begin_model_call()
                logger.info(
                    "Begin to attempt to send request: request_id=%s, attempt=%s",
                    request_id,
                    attempt,
                    extra={
                        "event": "model_call_started",
                        "request_id": request_id,
                        "model_call_index": attempt,
                        "attempt": attempt,
                    },
                )
                try:
                    stream = client.send_stream(trim_result.request)
                    model_response = await consume_stream(
                        stream, display_text, start_at, clock, request_timeout_config
                    )
                except asyncio.CancelledError:
                    observation.log_model_call(
                        logger,
                        None,
                        attempt=attempt,
                        failure_reason="request_cancelled",
                    )
                    raise
                except Exception:
                    observation.reason = "model_call_failed"
                    observation.log_model_call(logger, None, attempt=attempt)
                    raise
                observation.log_model_call(logger, model_response, attempt=attempt)
                if not can_retry_response(
                    model_response, attempt, request_retry_config
                ):
                    break
                parsed_retry_after = (
                    model_response.error.retry_after_seconds
                    if model_response.error is not None
                    else None
                )
                calculated_delay = calculate_retry_delay(
                    request_retry_config, attempt, parsed_retry_after, uniform
                )
                logger.info(
                    "Expected to wait for %f seconds: request_id=%s, attempt=%s, reason=%s",
                    calculated_delay,
                    request_id,
                    attempt,
                    model_response.reason,
                    extra={
                        "event": "retry_wait",
                        "request_id": request_id,
                        "attempt": attempt,
                        "reason": model_response.reason,
                        "planned_delay_seconds": calculated_delay,
                    },
                )
                await wait_before_retry(calculated_delay, deadline_at, clock, sleep)
        except (RequestStoppedError, asyncio.CancelledError) as stopped:
            if isinstance(stopped, asyncio.CancelledError):
                reason = ModelResponseEndReason.REQUEST_CANCELLED
                error = None
            else:
                reason = ModelResponseEndReason(stopped.reason.value)
                error = ModelResponseError(
                    code=reason,
                    message={
                        ModelResponseEndReason.REQUEST_DEADLINE_EXCEEDED: "The overall request deadline was exceeded.",
                        ModelResponseEndReason.INSUFFICIENT_RETRY_TIME: "Insufficient retry time. The request was not retried.",
                        ModelResponseEndReason.REQUEST_CANCELLED: "The request was cancelled.",
                    }[reason],
                )
            if model_response is None:
                model_response = ModelResponse(
                    text="",
                    reason=reason,
                    error=error,
                    usage=None,
                    timing=StreamResponseTiming(total_seconds=clock() - start_at),
                )
            else:
                model_response = replace(
                    model_response,
                    reason=reason,
                    error=error,
                    timing=replace(
                        model_response.timing, total_seconds=clock() - start_at
                    ),
                )
        observation.reason = model_response.reason
        observation.ttft_seconds = model_response.timing.ttft_seconds
        return model_response, trim_result


def print_text_delta(delta: str) -> None:
    terminal_output.write_text(delta)


@contextmanager
def _listen_for_cancel(
    prompt_session: PromptSession[str],
    on_cancel: Callable[[], None],
) -> Iterator[None]:
    terminal_input = prompt_session.app.input
    loop = asyncio.get_running_loop()
    escape_delay = prompt_session.app.ttimeoutlen
    flush_handle: asyncio.TimerHandle | None = None

    def handle_keys(keys: list[KeyPress]) -> None:
        if len(keys) == 1 and keys[0].key in (Keys.Escape, Keys.ControlC):
            on_cancel()

    def cancel_pending_flush() -> None:
        nonlocal flush_handle
        if flush_handle is not None:
            flush_handle.cancel()
            flush_handle = None

    def flush_pending_keys() -> None:
        nonlocal flush_handle
        flush_handle = None
        handle_keys(terminal_input.flush_keys())

    def on_input_ready() -> None:
        nonlocal flush_handle
        cancel_pending_flush()
        handle_keys(terminal_input.read_keys())
        flush_handle = loop.call_later(escape_delay, flush_pending_keys)

    try:
        with (
            terminal_input.raw_mode(),
            terminal_input.attach(on_input_ready),
        ):
            yield
    finally:
        cancel_pending_flush()


async def _run_stream_turn_with_cancel(
    *,
    prompt_session: PromptSession[str],
    client: ModelClient,
    config: ModelConfig,
    budgeter: Budgeter,
    system_message: Message,
    completed_turns: list[ConversationTurn],
    current_user_message: Message,
    reserved_output_tokens: int,
) -> tuple[ModelResponse, HistoryTrimResult]:
    """Run one stream turn with cancellation callbacks scoped to this call."""
    request_task: asyncio.Task[tuple[ModelResponse, HistoryTrimResult]] | None = None

    def request_cancelled_callback() -> None:
        if request_task is None:
            return
        if request_task.done():
            return
        if request_task.cancelling() > 0:
            return
        request_task.cancel()

    with _listen_for_cancel(prompt_session, request_cancelled_callback):
        request_task = asyncio.create_task(
            send_stream_conversation_turn(
                client=client,
                budgeter=budgeter,
                system_message=system_message,
                completed_turns=completed_turns,
                current_user_message=current_user_message,
                reserved_output_tokens=reserved_output_tokens,
                min_reserved_recent_turns=config.min_reserved_recent_turns,
                reasoning_effort=config.reasoning_effort,
                temperature=config.temperature,
                top_p=config.top_p,
                display_text=print_text_delta,
                request_timeout_config=config.request_timeout_config,
                request_retry_config=config.request_retry_config,
            )
        )
        return await request_task


async def _run_nonstream_turn_with_cancel(
    *,
    prompt_session: PromptSession[str],
    client: ModelClient,
    config: ModelConfig,
    budgeter: Budgeter,
    system_message: Message,
    completed_turns: list[ConversationTurn],
    current_user_message: Message,
    reserved_output_tokens: int,
    tools: list[ToolDefinition] | None = None,
    executor: ToolExecutor | None = None,
) -> tuple[ModelResponse, HistoryTrimResult]:
    cancel_event = Event()
    with _listen_for_cancel(prompt_session, cancel_event.set):
        worker_task = asyncio.create_task(
            asyncio.to_thread(
                send_conversation_turn,
                client=client,
                budgeter=budgeter,
                system_message=system_message,
                completed_turns=completed_turns,
                current_user_message=current_user_message,
                reserved_output_tokens=reserved_output_tokens,
                min_reserved_recent_turns=config.min_reserved_recent_turns,
                reasoning_effort=config.reasoning_effort,
                temperature=config.temperature,
                top_p=config.top_p,
                tools=tools,
                executor=executor,
                tool_loop_limits=config.tool_loop_limits,
                cancel_event=cancel_event,
                request_timeout_config=config.request_timeout_config,
            )
        )
        try:
            return await asyncio.shield(worker_task)
        except asyncio.CancelledError:
            cancel_event.set()
            await asyncio.gather(worker_task, return_exceptions=True)
            raise


async def talk(client: ModelClient, config: ModelConfig, budgeter: Budgeter):
    prompt_session = PromptSession()
    completed_turns: list[ConversationTurn] = []
    registry: ToolRegistry = create_default_tool_registry()
    tool_executor = ToolExecutor(tool_registry=registry)
    terminal_output.write_line("Please enter your prompt (type 'exit' to quit):\n")
    while True:
        user_input = await prompt_session.prompt_async("> ", multiline=False)
        if user_input.strip().lower() == "exit":
            terminal_output.write_line("Exiting...")
            return
        reserved_output_tokens = config.default_reserved_output_tokens
        system_msg = Message(role="system", content="You are a helpful assistant.")
        user_msg = Message(role="user", content=user_input)
        try:
            if config.stream_output_enabled:
                terminal_output.write_line("Model Response: ")
                model_response, trim_result = await _run_stream_turn_with_cancel(
                    prompt_session=prompt_session,
                    client=client,
                    config=config,
                    budgeter=budgeter,
                    system_message=system_msg,
                    completed_turns=completed_turns,
                    current_user_message=user_msg,
                    reserved_output_tokens=reserved_output_tokens,
                )
            else:
                model_response, trim_result = await _run_nonstream_turn_with_cancel(
                    prompt_session=prompt_session,
                    client=client,
                    config=config,
                    budgeter=budgeter,
                    system_message=system_msg,
                    completed_turns=completed_turns,
                    current_user_message=user_msg,
                    reserved_output_tokens=reserved_output_tokens,
                    tools=registry.get_tool_list(),
                    executor=tool_executor,
                )
        except BudgetRejectedError as error:
            logger.error(error.reason)
            if error.reason in (
                BudgetRejectionReason.MAX_INPUT_EXCEEDED,
                BudgetRejectionReason.CONTEXT_WINDOW_EXCEEDED,
            ):
                continue
            return
        except RequestStoppedError as error:
            if error.reason == RequestStopReason.REQUEST_CANCELLED:
                output_request_cancelled()
            elif error.reason == RequestStopReason.REQUEST_DEADLINE_EXCEEDED:
                terminal_output.write_line("The overall request deadline was exceeded.")
            continue
        except ToolLoopStoppedError as error:
            logger.error("Tool loop stopped due to: %s", error.reason.value)
            continue
        except ValueError:
            logger.error("Invalid conversation configuration.")
            return
        if (
            model_response.reason == ModelResponseEndReason.COMPLETED_NORMALLY
            and model_response.tool_calls
        ):
            terminal_output.write_line(
                "No final answer was produced. Additional tool calls remain pending."
            )
            continue
        completed_turns = trim_result.retained_completed_turns
        current_turn_start = 1 + sum(len(turn.items) for turn in completed_turns)
        current_turn_input = trim_result.request.input[current_turn_start:]
        assistant_msg = model_response_to_assistant_message(model_response)
        completed_turns.append(
            ConversationTurn(items=[*current_turn_input, assistant_msg])
        )
        if config.stream_output_enabled:
            terminal_output.write_line()
            output_response_status(model_response)
        else:
            output_model_response(model_response)


async def run_conversation(
    client: ModelClient, config: ModelConfig, budgeter: Budgeter
):
    try:
        await talk(client, config, budgeter)
    finally:
        await client.aclose()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[TerminalLogHandler(terminal_output)],
    )
    try:
        config = load_model_config()
    except ValueError:
        logger.error("Error loading model configuration.")
        return
    try:
        budgeter = create_budgeter(config)
    except ValueError:
        logger.error("Error creating budgeter.")
        return
    try:
        client = create_model_client(config)
    except ValueError:
        logger.error("Error creating model client.")
        return
    try:
        client.validate_reasoning_effort(
            config.reasoning_effort,
            config.model_profile.allowed_reasoning_efforts,
        )
    except ValueError:
        logger.error("Invalid reasoning effort configuration.")
        return
    asyncio.run(run_conversation(client, config, budgeter))


if __name__ == "__main__":
    main()

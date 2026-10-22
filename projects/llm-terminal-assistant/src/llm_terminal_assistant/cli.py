import asyncio
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
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
)
from llm_terminal_assistant.stream.consumer import consume_stream
from llm_terminal_assistant.terminal_output import TerminalLogHandler, TerminalOutput
from llm_terminal_assistant.tools.definition import ToolDefinition
from llm_terminal_assistant.tools.errors import ToolLoopStoppedError, ToolLoopStopReason
from llm_terminal_assistant.tools.executor import ToolExecutor
from llm_terminal_assistant.tools.factory import create_default_tool_registry
from llm_terminal_assistant.tools.loop import (
    ToolExecutionBudget,
    ToolLoopLimits,
    check_request_cancelled,
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


def output_model_response(response: ModelResponse):
    terminal_output.write_line("Model Response: ")
    if response.reason == ModelResponseEndReason.COMPLETED_NORMALLY:
        terminal_output.write_line(response.text)
    output_response_status(response)


def model_response_to_assistant_message(response: ModelResponse) -> Message:
    return Message(role="assistant", content=response.text)


def log_model_request_summary(request: ModelRequest) -> None:
    logger.info(
        "Model request: input_item_count=%d message_count=%d tool_call_count=%d tool_result_count=%d tool_definition_count=%d",
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
        "Budget check passed: estimated_input_tokens=%d reserved_output_tokens=%d safety_margin_tokens=%d remaining_tokens=%d",
        budget_result.estimated_input_tokens,
        budget_result.reserved_output_tokens,
        budget_result.safety_margin_tokens,
        budget_result.remaining_tokens,
    )
    log_model_request_summary(trim_result.request)
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
) -> tuple[ModelResponse, HistoryTrimResult]:
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
        )
        check_request_cancelled(cancel_event)
        response = client.send(trim_result.request)
        check_request_cancelled(cancel_event)
        return response, trim_result

    current_turn_input = [current_user_message]
    model_response, trim_result = trim_and_send(current_turn_input, completed_turns)
    if (
        model_response.reason != ModelResponseEndReason.COMPLETED_NORMALLY
        or not model_response.tool_calls
    ):
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
        )
        current_turn_start = len(model_request.input) - len(current_turn_input)
        current_turn_input = followup_request.input[current_turn_start:]
        model_response, trim_result = trim_and_send(
            current_turn_input,
            trim_result.retained_completed_turns,
        )
        tool_rounds += 1
        model_requests += 1
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
) -> tuple[ModelResponse, HistoryTrimResult]:
    start_at = clock()
    current_turn_input = [current_user_message]
    trim_result = _prepare_conversation_request(
        system_message,
        completed_turns,
        current_turn_input,
        reserved_output_tokens,
        min_reserved_recent_turns,
        budgeter,
        reasoning_effort,
        temperature,
        top_p,
    )
    stream = client.send_stream(trim_result.request)
    model_response = await consume_stream(
        stream, display_text, start_at, clock, request_timeout_config
    )
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
        except ToolLoopStoppedError as error:
            if error.reason == ToolLoopStopReason.REQUEST_CANCELLED:
                output_request_cancelled()
            else:
                logger.error("Tool loop stopped due to: %s", error.reason.value)
            continue
        except ValueError:
            logger.exception("Invalid conversation configuration.")
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
        logger.exception("Error loading model configuration.")
        return
    try:
        budgeter = create_budgeter(config)
    except ValueError:
        logger.exception("Error creating budgeter.")
        return
    try:
        client = create_model_client(config)
    except ValueError:
        logger.exception("Error creating model client.")
        return
    try:
        client.validate_reasoning_effort(
            config.reasoning_effort,
            config.model_profile.allowed_reasoning_efforts,
        )
    except ValueError:
        logger.exception("Invalid reasoning effort configuration.")
        return
    asyncio.run(run_conversation(client, config, budgeter))


if __name__ == "__main__":
    main()

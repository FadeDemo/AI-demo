from dataclasses import dataclass, replace

from llm_terminal_assistant.budgeter import (
    Budgeter,
    BudgetRejectedError,
    BudgetRejectionReason,
    BudgetResult,
)
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import (
    ModelInputItem,
    ModelRequest,
    ModelResponse,
    ModelResponseEndReason,
)
from llm_terminal_assistant.tools.definition import ToolDefinition
from llm_terminal_assistant.tools.executor import ToolExecutor
from llm_terminal_assistant.tools.loop import ToolExecutionBudget


@dataclass(frozen=True)
class ConversationTurn:
    items: list[ModelInputItem]


@dataclass
class HistoryTrimResult:
    request: ModelRequest
    budget_result: BudgetResult
    retained_completed_turns: list[ConversationTurn]
    dropped_completed_turns_count: int


def trim_history(
    system_message: Message,
    completed_turns: list[ConversationTurn],
    current_turn_input: list[ModelInputItem],
    reserved_output_tokens: int,
    min_reserved_recent_turns: int,
    budgeter: Budgeter,
    reasoning_effort: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    tools: list[ToolDefinition] | None = None,
) -> HistoryTrimResult:
    if min_reserved_recent_turns < 1:
        raise ValueError("min_reserved_recent_turns must be at least 1")
    retained_completed_turns = list(completed_turns)
    dropped_completed_turns_count = 0
    while True:
        messages = (
            [system_message]
            + [msg for turn in retained_completed_turns for msg in turn.items]
            + current_turn_input
        )
        model_request = ModelRequest(
            input=messages,
            reserved_output_tokens=reserved_output_tokens,
            reasoning_effort=reasoning_effort,
            temperature=temperature,
            top_p=top_p,
            tools=tools if tools is not None else [],
        )
        try:
            budget_result = budgeter.check(model_request)
            return HistoryTrimResult(
                request=model_request,
                budget_result=budget_result,
                retained_completed_turns=retained_completed_turns,
                dropped_completed_turns_count=dropped_completed_turns_count,
            )
        except BudgetRejectedError as error:
            if (
                error.reason
                not in (
                    BudgetRejectionReason.MAX_INPUT_EXCEEDED,
                    BudgetRejectionReason.CONTEXT_WINDOW_EXCEEDED,
                )
                or len(retained_completed_turns) <= min_reserved_recent_turns
            ):
                raise
            retained_completed_turns.pop(0)
            dropped_completed_turns_count += 1


def build_tool_followup_request(
    request: ModelRequest,
    response: ModelResponse,
    executor: ToolExecutor,
    tool_execution_budget: ToolExecutionBudget | None = None,
) -> ModelRequest:
    if response.reason != ModelResponseEndReason.COMPLETED_NORMALLY:
        raise ValueError(
            f"Cannot build tool follow-up request: response reason is {response.reason}"
        )
    if not response.tool_calls:
        raise ValueError("No tool calls found in the response")
    followup_request = replace(
        request,
        input=[
            *request.input,
            Message(role="assistant", content=response.text),
            *response.tool_calls,
        ],
    )
    for tool_call in response.tool_calls:
        followup_request.input.append(
            executor.execute_call(tool_call, tool_execution_budget)
        )
    return followup_request

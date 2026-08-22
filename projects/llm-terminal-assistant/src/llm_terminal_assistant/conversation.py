from dataclasses import dataclass

from llm_terminal_assistant.budgeter import (
    Budgeter,
    BudgetRejectedError,
    BudgetRejectionReason,
    BudgetResult,
)
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import ModelRequest


@dataclass(frozen=True)
class ConversationTurn:
    user_message: Message
    assistant_message: Message


@dataclass
class HistoryTrimResult:
    request: ModelRequest
    budget_result: BudgetResult
    retained_completed_turns: list[ConversationTurn]
    dropped_completed_turns_count: int


def trim_history(
    system_message: Message,
    completed_turns: list[ConversationTurn],
    current_user_message: Message,
    reserved_output_tokens: int,
    min_reserved_recent_turns: int,
    budgeter: Budgeter,
    reasoning_effort: str | None = None,
) -> HistoryTrimResult:
    if min_reserved_recent_turns < 1:
        raise ValueError("min_reserved_recent_turns must be at least 1")
    retained_completed_turns = list(completed_turns)
    dropped_completed_turns_count = 0
    while True:
        messages = (
            [system_message]
            + [
                msg
                for turn in retained_completed_turns
                for msg in (turn.user_message, turn.assistant_message)
            ]
            + [current_user_message]
        )
        model_request = ModelRequest(
            messages=messages,
            reserved_output_tokens=reserved_output_tokens,
            reasoning_effort=reasoning_effort,
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

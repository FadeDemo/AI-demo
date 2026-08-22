import logging

from llm_terminal_assistant.budgeter import (
    Budgeter,
    BudgetRejectedError,
    BudgetRejectionReason,
)
from llm_terminal_assistant.budgeter_factory import create_budgeter
from llm_terminal_assistant.client import ModelClient
from llm_terminal_assistant.client_factory import create_model_client
from llm_terminal_assistant.config import ModelConfig, load_model_config
from llm_terminal_assistant.conversation import (
    ConversationTurn,
    HistoryTrimResult,
    trim_history,
)
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import ModelResponse

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


def output_model_response(response: ModelResponse):
    print("Model Response: ")
    if response.reason == "Completed normally":
        print(response.text)
    else:
        print(response.reason)


def model_response_to_assistant_message(response: ModelResponse) -> Message:
    return Message(role="assistant", content=response.text)


def send_conversation_turn(
    client: ModelClient,
    budgeter: Budgeter,
    system_message: Message,
    completed_turns: list[ConversationTurn],
    current_user_message: Message,
    reserved_output_tokens: int,
    min_reserved_recent_turns: int,
    reasoning_effort: str | None = None,
) -> tuple[ModelResponse, HistoryTrimResult]:
    trim_result: HistoryTrimResult = trim_history(
        system_message=system_message,
        completed_turns=completed_turns,
        current_user_message=current_user_message,
        reserved_output_tokens=reserved_output_tokens,
        reasoning_effort=reasoning_effort,
        min_reserved_recent_turns=min_reserved_recent_turns,
        budgeter=budgeter,
    )
    budget_result = trim_result.budget_result
    logger.info(
        "Budget check passed: estimated_input_tokens=%d reserved_output_tokens=%d safety_margin_tokens=%d remaining_tokens=%d",
        budget_result.estimated_input_tokens,
        budget_result.reserved_output_tokens,
        budget_result.safety_margin_tokens,
        budget_result.remaining_tokens,
    )
    model_request = trim_result.request
    logger.info(
        "message_count=%d roles=%s content_lengths=%s",
        len(model_request.messages),
        [msg.role for msg in model_request.messages],
        [len(msg.content) for msg in model_request.messages],
    )
    model_response = client.send(model_request)
    return model_response, trim_result


def talk(client: ModelClient, config: ModelConfig, budgeter: Budgeter):
    completed_turns: list[ConversationTurn] = []
    print("Please enter your prompt (type 'exit' to quit):\n")
    while True:
        user_input = input("> ")
        if user_input.lower() == "exit":
            print("Exiting...")
            return
        reserved_output_tokens = config.default_reserved_output_tokens
        system_msg = Message(role="system", content="You are a helpful assistant.")
        user_msg = Message(role="user", content=user_input)
        try:
            model_response, trim_result = send_conversation_turn(
                client=client,
                budgeter=budgeter,
                system_message=system_msg,
                completed_turns=completed_turns,
                current_user_message=user_msg,
                reserved_output_tokens=reserved_output_tokens,
                min_reserved_recent_turns=config.min_reserved_recent_turns,
            )
        except BudgetRejectedError as error:
            logger.error(error.reason)
            if error.reason in (
                BudgetRejectionReason.MAX_INPUT_EXCEEDED,
                BudgetRejectionReason.CONTEXT_WINDOW_EXCEEDED,
            ):
                continue
            return
        except ValueError:
            logger.exception("Invalid conversation configuration.")
            return
        completed_turns = trim_result.retained_completed_turns
        assistant_msg = model_response_to_assistant_message(model_response)
        completed_turns.append(
            ConversationTurn(user_message=user_msg, assistant_message=assistant_msg)
        )
        output_model_response(model_response)


def main():
    config = load_model_config()
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

    talk(client, config, budgeter)


if __name__ == "__main__":
    main()

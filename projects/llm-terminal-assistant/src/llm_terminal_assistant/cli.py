import logging

from llm_terminal_assistant.budgeter import Budgeter, BudgetRejectedError
from llm_terminal_assistant.budgeter_factory import create_budgeter
from llm_terminal_assistant.client import ModelClient
from llm_terminal_assistant.client_factory import create_model_client
from llm_terminal_assistant.config import ModelConfig, load_model_config
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import ModelRequest, ModelResponse

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


def check_request_budget(budgeter: Budgeter, request: ModelRequest) -> bool:
    try:
        budget_result = budgeter.check(request)
        logger.info(
            "Budget check passed: estimated_input_tokens=%d reserved_output_tokens=%d safety_margin_tokens=%d remaining_tokens=%d",
            budget_result.estimated_input_tokens,
            budget_result.reserved_output_tokens,
            budget_result.safety_margin_tokens,
            budget_result.remaining_tokens,
        )
        return True
    except BudgetRejectedError as e:
        logger.error(e.reason)
        return False


def send_with_budget_check(
    client: ModelClient,
    budgeter: Budgeter,
    request: ModelRequest,
) -> ModelResponse | None:
    if not check_request_budget(budgeter, request):
        return None
    return client.send(request)


def talk(client: ModelClient, config: ModelConfig, budgeter: Budgeter):
    print("Please enter your prompt (type 'exit' to quit):\n")
    user_input = input("> ")
    if user_input.lower() == "exit":
        print("Exiting...")
        return
    reserved_output_tokens = config.default_reserved_output_tokens
    user_msg_list = []
    system_msg = Message(role="system", content="You are a helpful assistant.")
    user_msg = Message(role="user", content=user_input)
    user_msg_list.append(user_msg)
    model_request = ModelRequest(
        messages=[system_msg, user_msg], reserved_output_tokens=reserved_output_tokens
    )
    logger.info(
        "message_count=%d roles=%s content_lengths=%s",
        len(model_request.messages),
        [msg.role for msg in model_request.messages],
        [len(msg.content) for msg in model_request.messages],
    )
    model_response = send_with_budget_check(client, budgeter, model_request)
    if model_response is None:
        return
    output_model_response(model_response)
    user_input = input("> ")
    if user_input.lower() == "exit":
        print("Exiting...")
        return
    user_msg = Message(role="user", content=user_input)
    user_msg_list.append(user_msg)
    assistant_msg = model_response_to_assistant_message(model_response)
    model_request = ModelRequest(
        messages=[system_msg, user_msg_list[0], assistant_msg, user_msg_list[1]],
        reserved_output_tokens=reserved_output_tokens,
    )
    logger.info(
        "message_count=%d roles=%s content_lengths=%s",
        len(model_request.messages),
        [msg.role for msg in model_request.messages],
        [len(msg.content) for msg in model_request.messages],
    )
    model_response = send_with_budget_check(client, budgeter, model_request)
    if model_response is None:
        return
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

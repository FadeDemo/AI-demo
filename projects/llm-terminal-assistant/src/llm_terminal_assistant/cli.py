import logging

from llm_terminal_assistant.client import ModelClient
from llm_terminal_assistant.client_factory import create_model_client
from llm_terminal_assistant.config import load_model_config
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


def talk(client: ModelClient):
    print("Please enter your prompt (type 'exit' to quit):\n")
    user_input = input("> ")
    if user_input.lower() == "exit":
        print("Exiting...")
        return
    user_msg_list = []
    system_msg = Message(role="system", content="You are a helpful assistant.")
    user_msg = Message(role="user", content=user_input)
    user_msg_list.append(user_msg)
    model_request = ModelRequest(messages=[system_msg, user_msg])
    logger.info(
        "message_count=%d roles=%s content_lengths=%s",
        len(model_request.messages),
        [msg.role for msg in model_request.messages],
        [len(msg.content) for msg in model_request.messages],
    )
    model_response = client.send(model_request)
    output_model_response(model_response)
    user_input = input("> ")
    if user_input.lower() == "exit":
        print("Exiting...")
        return
    user_msg = Message(role="user", content=user_input)
    user_msg_list.append(user_msg)
    assistant_msg = model_response_to_assistant_message(model_response)
    model_request = ModelRequest(
        messages=[system_msg, user_msg_list[0], assistant_msg, user_msg_list[1]]
    )
    logger.info(
        "message_count=%d roles=%s content_lengths=%s",
        len(model_request.messages),
        [msg.role for msg in model_request.messages],
        [len(msg.content) for msg in model_request.messages],
    )
    model_response = client.send(model_request)
    output_model_response(model_response)


def main():
    try:
        client = create_model_client(load_model_config())
    except ValueError:
        logger.exception("Error creating model client.")
        return

    talk(client)


if __name__ == "__main__":
    main()

from llm_terminal_assistant.adapter.openai_client import OpenAIClient
from llm_terminal_assistant.config import load_model_config
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import (
    ModelRequest,
)


def main():
    print("Please enter your prompt (type 'exit' to quit):\n")
    user_input = input("> ")
    if user_input.lower() == "exit":
        print("Exiting...")
        return
    client = OpenAIClient(load_model_config())
    system_msg = Message(role="system", content="You are a helpful assistant.")
    user_msg = Message(role="user", content=user_input)
    model_request = ModelRequest(messages=[system_msg, user_msg])
    model_response = client.send(model_request)


if __name__ == "__main__":
    main()

from llm_terminal_assistant._vendor.deepseek_ai.deepseek_v4 import encode_messages
from llm_terminal_assistant.model import ModelRequest


def encode_deepseek_request(
    request: ModelRequest,
    thinking_mode: str,
) -> str:
    messages = [
        {
            "role": message.role,
            "content": message.content,
        }
        for message in request.messages
    ]

    return encode_messages(
        messages=messages,
        thinking_mode=thinking_mode,
    )

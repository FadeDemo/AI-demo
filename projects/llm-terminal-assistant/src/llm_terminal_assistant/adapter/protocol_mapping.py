from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import ModelInputItem
from llm_terminal_assistant.tools.protocol import ToolCallRequest, ToolCallResult


def to_openai_responses_input_item(item: ModelInputItem) -> dict[str, object]:
    match item:
        case Message(role=role, content=content):
            return {"role": role, "content": content}
        case ToolCallRequest(call_id=call_id, name=name, arguments=arguments):
            return {
                "type": "function_call",
                "call_id": call_id,
                "name": name,
                "arguments": arguments,
            }
        case ToolCallResult(call_id=call_id, output=output):
            return {
                "type": "function_call_output",
                "call_id": call_id,
                "output": output,
            }
        case _:
            raise TypeError(f"Unsupported input item type: {type(item).__name__}")

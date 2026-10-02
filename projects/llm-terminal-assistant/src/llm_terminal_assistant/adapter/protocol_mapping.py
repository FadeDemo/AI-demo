from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import ModelInputItem, ModelRequest
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


def to_deepseek_messages(
    request: ModelRequest,
) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []
    items = request.input
    if not items:
        return messages

    i = 0
    while i < len(items):
        item = items[i]
        match item:
            case Message(role=role, content=content):
                messages.append({"role": role, "content": content})
            case ToolCallRequest(call_id=call_id, name=name, arguments=arguments):
                if messages and messages[-1]["role"] == "assistant":
                    assistant_message = messages[-1]
                else:
                    assistant_message = {"role": "assistant", "content": ""}
                    next_item = items[i + 1] if i + 1 < len(items) else None
                    if isinstance(next_item, Message) and next_item.role == "assistant":
                        assistant_message["content"] = next_item.content
                        i += 1
                    messages.append(assistant_message)

                assistant_message.setdefault("tool_calls", []).append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": arguments,
                        },
                    }
                )
            case ToolCallResult(call_id=call_id, output=output):
                messages.append(
                    {"role": "tool", "tool_call_id": call_id, "content": output}
                )
        i += 1

    if request.tools:
        if messages[0]["role"] != "system":
            messages.insert(0, {"role": "system", "content": ""})
        messages[0]["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameter_schema,
                },
            }
            for tool in request.tools
        ]

    return messages

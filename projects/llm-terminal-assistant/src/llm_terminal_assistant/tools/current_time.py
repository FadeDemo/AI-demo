from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from llm_terminal_assistant.tools.definition import (
    RegisteredTool,
    ToolArguments,
    ToolDefinition,
    ToolOutput,
)
from llm_terminal_assistant.tools.errors import InvalidToolArgumentsError

type Clock = Callable[[], datetime]


def system_clock() -> datetime:
    return datetime.now(UTC)


def get_current_time(timezone: str, clock: Clock) -> ToolOutput:
    try:
        timezone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as e:
        raise InvalidToolArgumentsError("Invalid timezone") from e
    now = clock().astimezone(timezone)
    return {"timezone": timezone.key, "current_time": now.isoformat()}


def create_current_time_tool(clock: Clock) -> RegisteredTool:
    def handler(args: ToolArguments) -> ToolOutput:
        return get_current_time(args["timezone"], clock)

    return RegisteredTool(
        definition=ToolDefinition(
            name="get_current_time",
            description="Returns the current time in ISO 8601 format.",
            parameter_schema={
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "required": ["timezone"],
                "properties": {
                    "timezone": {
                        "type": "string",
                        "minLength": 1,
                    }
                },
            },
        ),
        handler=handler,
    )

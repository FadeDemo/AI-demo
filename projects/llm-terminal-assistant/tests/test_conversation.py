import unittest

from llm_terminal_assistant.budgeter import (
    Budgeter,
    BudgetRejectedError,
    BudgetRejectionReason,
)
from llm_terminal_assistant.cli import send_conversation_turn
from llm_terminal_assistant.conversation import ConversationTurn
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import (
    InputTokensDetails,
    ModelLimits,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    OutputTokensDetails,
)


class ContentRequestEncoder:
    def __init__(self):
        self.requests: list[ModelRequest] = []

    def encode_request(self, request: ModelRequest) -> str:
        self.requests.append(request)
        return "".join(message.content for message in request.messages)


class TextLengthTokenCounter:
    def __init__(self):
        self.received_texts: list[str] = []

    def count_tokens(
        self,
        text: str,
        add_special_tokens: bool = False,
    ) -> int:
        self.received_texts.append(text)
        return len(text)


class SpyModelClient:
    def __init__(self):
        self.requests: list[ModelRequest] = []

    def send(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(
            text="fake response",
            reason="Completed normally",
            usage=ModelUsage(
                input_tokens=0,
                input_tokens_details=InputTokensDetails(
                    cached_tokens=0,
                    cache_write_tokens=0,
                ),
                output_tokens=0,
                output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
                total_tokens=0,
            ),
        )


def make_turn(index: int) -> ConversationTurn:
    return ConversationTurn(
        user_message=Message(role="user", content=f"u{index}".ljust(10, "u")),
        assistant_message=Message(
            role="assistant",
            content=f"a{index}".ljust(10, "a"),
        ),
    )


def make_six_turns() -> list[ConversationTurn]:
    return [make_turn(index) for index in range(1, 7)]


def flatten_turns(turns: list[ConversationTurn]) -> list[Message]:
    return [
        message
        for turn in turns
        for message in (turn.user_message, turn.assistant_message)
    ]


def make_budgeter(
    *,
    context_window_tokens: int,
    max_input_tokens: int | None = None,
    max_output_tokens: int | None = 100,
) -> tuple[Budgeter, ContentRequestEncoder]:
    encoder = ContentRequestEncoder()
    return (
        Budgeter(
            token_counter=TextLengthTokenCounter(),
            request_encoder=encoder,
            model_limits=ModelLimits(
                context_window_tokens=context_window_tokens,
                max_input_tokens=max_input_tokens,
                max_output_tokens=max_output_tokens,
            ),
            safety_margin_tokens=0,
        ),
        encoder,
    )


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.system_message = Message(role="system", content="s" * 10)
        self.current_user_message = Message(role="user", content="c" * 10)
        self.completed_turns = make_six_turns()
        self.client = SpyModelClient()

    def send_turn(
        self,
        budgeter: Budgeter,
        *,
        min_recent_turns: int = 2,
        reserved_output_tokens: int = 10,
    ):
        return send_conversation_turn(
            client=self.client,
            budgeter=budgeter,
            system_message=self.system_message,
            completed_turns=self.completed_turns,
            current_user_message=self.current_user_message,
            reserved_output_tokens=reserved_output_tokens,
            min_reserved_recent_turns=min_recent_turns,
        )

    def test_six_budgeted_turns_remain_unchanged_and_send_once(self):
        budgeter, encoder = make_budgeter(context_window_tokens=150)

        response, trim_result = self.send_turn(budgeter)

        self.assertEqual(response.text, "fake response")
        self.assertEqual(self.client.requests, [trim_result.request])
        self.assertEqual(encoder.requests, [trim_result.request])
        self.assertEqual(trim_result.retained_completed_turns, self.completed_turns)
        self.assertIsNot(
            trim_result.retained_completed_turns,
            self.completed_turns,
        )
        self.assertEqual(trim_result.dropped_completed_turns_count, 0)
        self.assertEqual(trim_result.budget_result.remaining_tokens, 0)

    def test_context_excess_drops_oldest_complete_turns(self):
        original_turns = list(self.completed_turns)
        budgeter, encoder = make_budgeter(context_window_tokens=110)

        _, trim_result = self.send_turn(budgeter)

        expected_turns = original_turns[2:]
        expected_messages = [
            self.system_message,
            *flatten_turns(expected_turns),
            self.current_user_message,
        ]
        self.assertEqual(trim_result.retained_completed_turns, expected_turns)
        self.assertEqual(trim_result.request.messages, expected_messages)
        self.assertEqual(trim_result.dropped_completed_turns_count, 2)
        self.assertEqual(trim_result.budget_result.remaining_tokens, 0)
        self.assertEqual(len(encoder.requests), 3)
        self.assertEqual(self.client.requests, [trim_result.request])
        self.assertEqual(self.completed_turns, original_turns)

    def test_max_input_excess_drops_oldest_complete_turns(self):
        budgeter, encoder = make_budgeter(
            context_window_tokens=1_000,
            max_input_tokens=100,
        )

        _, trim_result = self.send_turn(budgeter)

        self.assertEqual(
            trim_result.retained_completed_turns,
            self.completed_turns[2:],
        )
        self.assertEqual(trim_result.budget_result.estimated_input_tokens, 100)
        self.assertEqual(trim_result.dropped_completed_turns_count, 2)
        self.assertEqual(len(encoder.requests), 3)
        self.assertEqual(self.client.requests, [trim_result.request])

    def test_required_content_rejection_does_not_call_client(self):
        original_turns = list(self.completed_turns)
        budgeter, encoder = make_budgeter(context_window_tokens=69)

        with self.assertRaises(BudgetRejectedError) as caught:
            self.send_turn(budgeter)

        self.assertEqual(
            caught.exception.reason,
            BudgetRejectionReason.CONTEXT_WINDOW_EXCEEDED,
        )
        self.assertEqual(len(encoder.requests), 5)
        self.assertEqual(self.client.requests, [])
        self.assertEqual(self.completed_turns, original_turns)

    def test_nontrimmable_rejections_do_not_call_client(self):
        cases = (
            (
                "negative limit",
                make_budgeter(context_window_tokens=-1)[0],
                BudgetRejectionReason.NEGATIVE_LIMIT,
            ),
            (
                "maximum output",
                make_budgeter(
                    context_window_tokens=1_000,
                    max_output_tokens=5,
                )[0],
                BudgetRejectionReason.MAX_OUTPUT_EXCEEDED,
            ),
        )

        for name, budgeter, expected_reason in cases:
            with self.subTest(name=name):
                with self.assertRaises(BudgetRejectedError) as caught:
                    self.send_turn(budgeter)

                self.assertEqual(caught.exception.reason, expected_reason)
                self.assertEqual(self.client.requests, [])

    def test_invalid_minimum_recent_turns_do_not_call_client(self):
        budgeter, encoder = make_budgeter(context_window_tokens=1_000)

        for invalid_value in (0, -1):
            with (
                self.subTest(
                    invalid_value=invalid_value,
                ),
                self.assertRaisesRegex(ValueError, "must be at least 1"),
            ):
                self.send_turn(
                    budgeter,
                    min_recent_turns=invalid_value,
                )

        self.assertEqual(encoder.requests, [])
        self.assertEqual(self.client.requests, [])


if __name__ == "__main__":
    unittest.main()

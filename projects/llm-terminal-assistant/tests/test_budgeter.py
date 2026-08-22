import unittest

from llm_terminal_assistant.adapter.deepseek_prompt_encoder import (
    DeepSeekRequestEncoder,
)
from llm_terminal_assistant.budgeter import (
    Budgeter,
    BudgetRejectedError,
    BudgetRejectionReason,
)
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import ModelLimits, ModelRequest


class FixedTokenCounter:
    def __init__(self, token_count: int):
        self.token_count = token_count
        self.received_texts: list[str] = []

    def count_tokens(
        self,
        text: str,
        add_special_tokens: bool = False,
    ) -> int:
        self.received_texts.append(text)
        return self.token_count


class StubRequestEncoder:
    def __init__(self, encoded_request: str = "encoded-request"):
        self.encoded_request = encoded_request
        self.requests: list[ModelRequest] = []

    def encode_request(self, request: ModelRequest) -> str:
        self.requests.append(request)
        return self.encoded_request


def make_request(reserved_output_tokens: int = 20) -> ModelRequest:
    return ModelRequest(
        messages=[
            Message(role="system", content="system instruction"),
            Message(role="user", content="user question"),
        ],
        reserved_output_tokens=reserved_output_tokens,
    )


def make_budgeter(
    estimated_input_tokens: int,
    *,
    model_limits: ModelLimits | None = None,
    safety_margin_tokens: int = 10,
) -> tuple[Budgeter, FixedTokenCounter, StubRequestEncoder]:
    counter = FixedTokenCounter(estimated_input_tokens)
    encoder = StubRequestEncoder()
    budgeter = Budgeter(
        token_counter=counter,
        request_encoder=encoder,
        model_limits=model_limits
        or ModelLimits(
            context_window_tokens=100,
            max_input_tokens=80,
            max_output_tokens=30,
        ),
        safety_margin_tokens=safety_margin_tokens,
    )
    return budgeter, counter, encoder


class BudgeterTests(unittest.TestCase):
    def test_budgeted_request_returns_result(self):
        request = make_request()
        budgeter, counter, encoder = make_budgeter(estimated_input_tokens=60)

        result = budgeter.check(request)

        self.assertEqual(result.estimated_input_tokens, 60)
        self.assertEqual(result.remaining_tokens, 10)
        self.assertEqual(encoder.requests, [request])
        self.assertEqual(counter.received_texts, [encoder.encoded_request])

    def test_zero_remaining_tokens_is_allowed(self):
        request = make_request()
        budgeter, _, _ = make_budgeter(estimated_input_tokens=70)

        result = budgeter.check(request)

        self.assertEqual(result.remaining_tokens, 0)

    def test_context_window_excess_is_rejected(self):
        request = make_request()
        budgeter, _, _ = make_budgeter(estimated_input_tokens=71)

        with self.assertRaises(BudgetRejectedError) as caught:
            budgeter.check(request)

        self.assertEqual(
            caught.exception.reason,
            BudgetRejectionReason.CONTEXT_WINDOW_EXCEEDED,
        )

    def test_max_input_excess_is_rejected(self):
        request = make_request()
        limits = ModelLimits(
            context_window_tokens=100,
            max_input_tokens=50,
            max_output_tokens=30,
        )
        budgeter, _, _ = make_budgeter(51, model_limits=limits)

        with self.assertRaises(BudgetRejectedError) as caught:
            budgeter.check(request)

        self.assertEqual(
            caught.exception.reason,
            BudgetRejectionReason.MAX_INPUT_EXCEEDED,
        )

    def test_max_output_excess_is_rejected(self):
        request = make_request(reserved_output_tokens=31)
        budgeter, _, _ = make_budgeter(estimated_input_tokens=20)

        with self.assertRaises(BudgetRejectedError) as caught:
            budgeter.check(request)

        self.assertEqual(
            caught.exception.reason,
            BudgetRejectionReason.MAX_OUTPUT_EXCEEDED,
        )

    def test_negative_limits_are_rejected(self):
        cases = (
            (
                "context window",
                ModelLimits(-1, max_input_tokens=80, max_output_tokens=30),
                20,
                10,
            ),
            (
                "reserved output",
                ModelLimits(100, max_input_tokens=80, max_output_tokens=30),
                -1,
                10,
            ),
            (
                "safety margin",
                ModelLimits(100, max_input_tokens=80, max_output_tokens=30),
                20,
                -1,
            ),
            (
                "max input",
                ModelLimits(100, max_input_tokens=-1, max_output_tokens=30),
                20,
                10,
            ),
            (
                "max output",
                ModelLimits(100, max_input_tokens=80, max_output_tokens=-1),
                20,
                10,
            ),
        )

        for name, limits, reserved_output_tokens, safety_margin_tokens in cases:
            with self.subTest(name=name):
                request = make_request(reserved_output_tokens)
                budgeter, _, _ = make_budgeter(
                    20,
                    model_limits=limits,
                    safety_margin_tokens=safety_margin_tokens,
                )

                with self.assertRaises(BudgetRejectedError) as caught:
                    budgeter.check(request)

                self.assertEqual(
                    caught.exception.reason,
                    BudgetRejectionReason.NEGATIVE_LIMIT,
                )

    def test_real_encoder_includes_system_message_and_message_wrappers(self):
        request = ModelRequest(
            messages=[
                Message(role="system", content="SYSTEM_SENTINEL"),
                Message(role="user", content="USER_SENTINEL"),
            ],
            reserved_output_tokens=20,
        )
        estimated_input_tokens = 10
        counter = FixedTokenCounter(estimated_input_tokens)
        budgeter = Budgeter(
            token_counter=counter,
            request_encoder=DeepSeekRequestEncoder(default_reasoning_effort="high"),
            model_limits=ModelLimits(context_window_tokens=100),
            safety_margin_tokens=0,
        )

        result = budgeter.check(request)

        self.assertEqual(result.estimated_input_tokens, estimated_input_tokens)
        self.assertEqual(len(counter.received_texts), 1)
        encoded_request = counter.received_texts[0]
        separator = "\N{FULLWIDTH VERTICAL LINE}"
        self.assertIn("SYSTEM_SENTINEL", encoded_request)
        self.assertIn(f"<{separator}User{separator}>USER_SENTINEL", encoded_request)
        self.assertIn(f"<{separator}Assistant{separator}>", encoded_request)


if __name__ == "__main__":
    unittest.main()

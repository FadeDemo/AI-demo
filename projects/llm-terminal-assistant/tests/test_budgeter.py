import unittest

from llm_terminal_assistant.adapter.deepseek_prompt_encoder import (
    DeepSeekRequestEncoder,
)
from llm_terminal_assistant.budgeter import Budgeter, BudgetRejectedError
from llm_terminal_assistant.cli import send_with_budget_check
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import (
    InputTokensDetails,
    ModelLimits,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    OutputTokensDetails,
)


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
    def test_budgeted_request_calls_client_once(self):
        request = make_request()
        budgeter, counter, encoder = make_budgeter(estimated_input_tokens=60)
        client = SpyModelClient()

        response = send_with_budget_check(client, budgeter, request)

        self.assertIsNotNone(response)
        self.assertEqual(client.requests, [request])
        self.assertEqual(encoder.requests, [request])
        self.assertEqual(counter.received_texts, [encoder.encoded_request])

    def test_zero_remaining_tokens_still_calls_client_once(self):
        request = make_request()
        budgeter, _, _ = make_budgeter(estimated_input_tokens=70)
        client = SpyModelClient()

        result = budgeter.check(request)
        response = send_with_budget_check(client, budgeter, request)

        self.assertEqual(result.remaining_tokens, 0)
        self.assertIsNotNone(response)
        self.assertEqual(client.requests, [request])

    def test_context_window_excess_does_not_call_client(self):
        request = make_request()
        budgeter, _, _ = make_budgeter(estimated_input_tokens=71)
        client = SpyModelClient()

        with self.assertRaisesRegex(BudgetRejectedError, "context_window_exceeded"):
            budgeter.check(request)
        with self.assertLogs("llm_terminal_assistant.cli", level="ERROR"):
            response = send_with_budget_check(client, budgeter, request)

        self.assertIsNone(response)
        self.assertEqual(client.requests, [])

    def test_max_input_excess_does_not_call_client(self):
        request = make_request()
        limits = ModelLimits(
            context_window_tokens=100,
            max_input_tokens=50,
            max_output_tokens=30,
        )
        budgeter, _, _ = make_budgeter(51, model_limits=limits)
        client = SpyModelClient()

        with self.assertRaises(BudgetRejectedError) as caught:
            budgeter.check(request)
        with self.assertLogs("llm_terminal_assistant.cli", level="ERROR"):
            response = send_with_budget_check(client, budgeter, request)

        self.assertEqual(caught.exception.reason, "max_input_exceeded")
        self.assertIsNone(response)
        self.assertEqual(client.requests, [])

    def test_max_output_excess_does_not_call_client(self):
        request = make_request(reserved_output_tokens=31)
        budgeter, _, _ = make_budgeter(estimated_input_tokens=20)
        client = SpyModelClient()

        with self.assertRaises(BudgetRejectedError) as caught:
            budgeter.check(request)
        with self.assertLogs("llm_terminal_assistant.cli", level="ERROR"):
            response = send_with_budget_check(client, budgeter, request)

        self.assertEqual(caught.exception.reason, "max_output_exceeded")
        self.assertIsNone(response)
        self.assertEqual(client.requests, [])

    def test_negative_limits_do_not_call_client(self):
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
                client = SpyModelClient()

                with self.assertRaises(BudgetRejectedError) as caught:
                    budgeter.check(request)
                with self.assertLogs("llm_terminal_assistant.cli", level="ERROR"):
                    response = send_with_budget_check(client, budgeter, request)

                self.assertEqual(caught.exception.reason, "negative_limit")
                self.assertIsNone(response)
                self.assertEqual(client.requests, [])

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

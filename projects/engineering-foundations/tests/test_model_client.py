from unittest.mock import Mock


def answer_question(question: str, model_client) -> str:
    return model_client.generate(question)


class StubModelClient:
    def generate(self, question: str) -> str:
        return "fixed answer"


class FakeModelClient:
    def __init__(self, answers: dict[str, str]):
        self.answers = answers

    def generate(self, question: str) -> str:
        return self.answers.get(question, "I do not know")


def test_answer_question_with_stub():
    client = StubModelClient()

    answer = answer_question("What is RAG?", client)

    assert answer == "fixed answer"


def test_answer_question_with_fake():
    client = FakeModelClient({"What is RAG?": "Retrieval-augmented generation"})

    answer = answer_question("What is RAG?", client)

    assert answer == "Retrieval-augmented generation"


def test_answer_question_calls_model_client():
    client = Mock()
    client.generate.return_value = "fixed answer"

    answer = answer_question("What is RAG?", client)

    assert answer == "fixed answer"
    client.generate.assert_called_once_with("What is RAG?")

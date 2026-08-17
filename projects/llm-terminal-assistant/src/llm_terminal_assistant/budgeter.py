from llm_terminal_assistant.token_counter import TokenCounter


class Budgeter:
    def __init__(self, token_counter: TokenCounter):
        self.token_counter = token_counter

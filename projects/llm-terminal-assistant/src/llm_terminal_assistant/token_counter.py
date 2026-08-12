from typing import Protocol


class TokenCounter(Protocol):
    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in the given text."""
        ...

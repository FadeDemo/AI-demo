from typing import Protocol


class TokenCounter(Protocol):
    def count_tokens(
        self,
        text: str,
        add_special_tokens: bool = False,
    ) -> int:
        """Count the number of tokens in the given text."""
        ...

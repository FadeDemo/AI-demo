from dataclasses import dataclass

from transformers import AutoTokenizer, PreTrainedTokenizerBase

from llm_terminal_assistant.model import ModelProfile
from llm_terminal_assistant.token_counter import TokenCounter


def load_huggingface_tokenizer(model_profile: ModelProfile) -> PreTrainedTokenizerBase:
    """
    Loads the tokenizer for the specified model profile from Hugging Face.

    Args:
        model_profile (ModelProfile): The profile of the model for which to load the tokenizer.

    Returns:
        PreTrainedTokenizerBase: The tokenizer for the using model from Hugging Face.
    """
    return AutoTokenizer.from_pretrained(
        model_profile.repository, revision=model_profile.revision
    )


@dataclass
class HuggingFaceTokenCounter(TokenCounter):
    tokenizer: PreTrainedTokenizerBase

    def count_tokens(
        self,
        text: str,
        add_special_tokens: bool = False,
    ) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=add_special_tokens))

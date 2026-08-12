from dataclasses import dataclass

from transformers import AutoTokenizer, PreTrainedTokenizerBase

from llm_terminal_assistant.model import MODEL_PROFILES
from llm_terminal_assistant.token_counter import TokenCounter


def load_huggingface_tokenizer(api_model_id: str) -> PreTrainedTokenizerBase:
    """
    Returns the tokenizer for the using model from Hugging Face.

    Returns:
        PreTrainedTokenizerBase: The tokenizer for the using model from Hugging Face.
    """
    model_profile = MODEL_PROFILES.get(api_model_id)
    if not model_profile:
        raise ValueError(f"Model profile for {api_model_id} not found.")
    return AutoTokenizer.from_pretrained(
        model_profile.repository, revision=model_profile.revision
    )


@dataclass
class HuggingFaceTokenCounter(TokenCounter):
    tokenizer: PreTrainedTokenizerBase

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=False))

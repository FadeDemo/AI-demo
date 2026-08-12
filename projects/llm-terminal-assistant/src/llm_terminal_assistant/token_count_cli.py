from importlib.metadata import version
from pathlib import Path

from llm_terminal_assistant.adapter.huggingface_tokenizer import (
    HuggingFaceTokenCounter,
    load_huggingface_tokenizer,
)
from llm_terminal_assistant.config import load_model_config
from llm_terminal_assistant.model import MODEL_PROFILES

PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "samples" / "token-counting"


def main():
    model_config = load_model_config()
    print(
        f"Using model: {model_config.model}, repository: {MODEL_PROFILES[model_config.model].repository}, revision: {MODEL_PROFILES[model_config.model].revision}, transformers version: {version('transformers')}, tokenizers version: {version('tokenizers')}"
    )
    tokenizer = load_huggingface_tokenizer(model_config.model)
    token_counter = HuggingFaceTokenCounter(tokenizer=tokenizer)
    chinese_sample_path = DATA_DIR / "chinese.txt"
    chinese_text = chinese_sample_path.read_text(encoding="utf-8")
    print(f"Sample: {chinese_sample_path.relative_to(PROJECT_DIR)}")
    print(f"For Chinese text:\n{chinese_text}")
    print(f"Character count: {len(chinese_text)}")
    print(f"Token count: {token_counter.count_tokens(chinese_text)}\n")
    english_sample_path = DATA_DIR / "english.txt"
    print(f"Sample: {english_sample_path.relative_to(PROJECT_DIR)}")
    english_text = english_sample_path.read_text(encoding="utf-8")
    print(f"For English text:\n{english_text}")
    print(f"Character count: {len(english_text)}")
    print(f"Token count: {token_counter.count_tokens(english_text)}\n")
    json_sample_path = DATA_DIR / "data.json"
    json_text = json_sample_path.read_text(encoding="utf-8")
    print(f"Sample: {json_sample_path.relative_to(PROJECT_DIR)}")
    print(f"For JSON text:\n{json_text}")
    print(f"Character count: {len(json_text)}")
    print(f"Token count: {token_counter.count_tokens(json_text)}\n")
    code_sample_path = DATA_DIR / "example.py"
    print(f"Sample: {code_sample_path.relative_to(PROJECT_DIR)}")
    code_text = code_sample_path.read_text(encoding="utf-8")
    print(f"Character count: {len(code_text)}")
    print(f"For Python code:\n{code_text}")
    print(f"Token count: {token_counter.count_tokens(code_text)}\n")


if __name__ == "__main__":
    main()

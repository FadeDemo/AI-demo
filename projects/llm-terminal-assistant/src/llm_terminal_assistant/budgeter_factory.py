from llm_terminal_assistant.adapter.deepseek_prompt_encoder import (
    DeepSeekRequestEncoder,
)
from llm_terminal_assistant.budgeter import Budgeter
from llm_terminal_assistant.config import ModelConfig
from llm_terminal_assistant.model import (
    FAKE_MODEL_ID,
    FAKE_MODEL_LIMITS,
    MODEL_PROFILES,
)


def create_budgeter(config: ModelConfig) -> Budgeter:
    if config.model == FAKE_MODEL_ID:
        if config.provider != "faked":
            raise ValueError("The fake model requires the faked provider.")

        from llm_terminal_assistant.adapter.fake_model import (
            CodePointTokenCounter,
            FakeModelRequestEncoder,
        )

        return Budgeter(
            token_counter=CodePointTokenCounter(),
            request_encoder=FakeModelRequestEncoder(),
            model_limits=FAKE_MODEL_LIMITS,
            safety_margin_tokens=config.safety_margin_tokens,
        )

    model_profile = MODEL_PROFILES.get(config.model)
    if model_profile is None:
        raise ValueError(f"Model profile for {config.model} not found.")

    from llm_terminal_assistant.adapter.huggingface_tokenizer import (
        HuggingFaceTokenCounter,
        load_huggingface_tokenizer,
    )

    token_counter = HuggingFaceTokenCounter(
        tokenizer=load_huggingface_tokenizer(config.model)
    )
    request_encoder = DeepSeekRequestEncoder(
        default_reasoning_effort=model_profile.default_reasoning_effort
    )
    return Budgeter(
        token_counter=token_counter,
        request_encoder=request_encoder,
        model_limits=model_profile.limit,
        safety_margin_tokens=config.safety_margin_tokens,
    )

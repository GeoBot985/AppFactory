from dataclasses import dataclass

from src.prompt.prompt_profiles import (
    DEFAULT_STRICT,
    GEMMA_UCI_HARDLINE,
    PromptProfile,
)


@dataclass(frozen=True)
class ModelPromptSettings:
    profile: PromptProfile
    custom_instructions: str = ""


MODEL_PROMPT_SETTINGS = {
    "gemma3:1b": ModelPromptSettings(
        profile=GEMMA_UCI_HARDLINE,
        custom_instructions=(
            "You often drift into move text or shorthand. Do not do that here.\n"
            "Choose one option number only.\n"
            "Do not answer with Qxd8+, Nf6, Bd7, Rh8, g8, h8, or any UCI move text.\n"
            "Return only the number of the chosen option.\n"
            "If a capture wins material immediately, prefer that capture over a quiet move."
        ),
    ),
    "gemma3:4b": ModelPromptSettings(
        profile=GEMMA_UCI_HARDLINE,
        custom_instructions=(
            "Use the numbered legal move options exactly as written.\n"
            "Choose one option number only.\n"
            "Do not answer with SAN captures such as Qxd8+ or exd6.\n"
            "Do not type the move itself.\n"
            "If an undefended enemy piece can be captured safely in one move, prefer that capture."
        ),
    ),
    "granite4:1b": ModelPromptSettings(
        profile=DEFAULT_STRICT,
        custom_instructions=(
            "Do not repeat an earlier move if that piece is no longer on the same square.\n"
            "Verify the move against the current board before replying.\n"
            "Before replying, check whether you can win material or give check immediately.\n"
            "Do not output a move for the wrong color. If White is to move, do not answer with moves like e5 or Nc6.\n"
            "Before sending your answer, compare it against the legal move options and return only the chosen option number."
        ),
    ),
    "granite4:3b": ModelPromptSettings(
        profile=DEFAULT_STRICT,
        custom_instructions=(
            "Check the current board state before answering.\n"
            "Return only one option number from the legal move list.\n"
            "Before choosing a quiet move, check whether a legal capture wins material.\n"
            "Do not output a move for the wrong color. If White is to move, do not answer with moves like e5 or Nc6.\n"
            "Before sending your answer, compare it against the legal move options and return only the chosen option number."
        ),
    ),
}


def get_model_prompt_settings(model_name: str) -> ModelPromptSettings:
    lowered = model_name.lower()
    if lowered in MODEL_PROMPT_SETTINGS:
        return MODEL_PROMPT_SETTINGS[lowered]
    return ModelPromptSettings(profile=DEFAULT_STRICT, custom_instructions="")

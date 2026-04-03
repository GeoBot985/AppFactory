from dataclasses import dataclass


@dataclass(frozen=True)
class PromptProfile:
    name: str
    include_fen: bool
    include_ascii_board: bool
    include_move_history: bool
    include_legal_moves: bool
    move_output_mode: str
    legal_moves_format: str
    history_format: str
    board_style: str
    strict_output_mode: bool
    max_history_moves: int
    retry_tone: str
    output_reminder: str = ""


DEFAULT_STRICT = PromptProfile(
    name="DEFAULT_STRICT",
    include_fen=True,
    include_ascii_board=True,
    include_move_history=True,
    include_legal_moves=True,
    move_output_mode="index",
    legal_moves_format="comma",
    history_format="san",
    board_style="compact",
    strict_output_mode=True,
    max_history_moves=6,
    retry_tone="firm",
)

COMPACT_HARDLINE = PromptProfile(
    name="COMPACT_HARDLINE",
    include_fen=True,
    include_ascii_board=False,
    include_move_history=False,
    include_legal_moves=True,
    move_output_mode="index",
    legal_moves_format="space",
    history_format="uci",
    board_style="compact",
    strict_output_mode=True,
    max_history_moves=0,
    retry_tone="strict",
)

READABLE_BOARD = PromptProfile(
    name="READABLE_BOARD",
    include_fen=True,
    include_ascii_board=True,
    include_move_history=True,
    include_legal_moves=True,
    move_output_mode="index",
    legal_moves_format="lines",
    history_format="san",
    board_style="full",
    strict_output_mode=True,
    max_history_moves=8,
    retry_tone="firm",
)

GEMMA_UCI_HARDLINE = PromptProfile(
    name="GEMMA_UCI_HARDLINE",
    include_fen=True,
    include_ascii_board=True,
    include_move_history=True,
    include_legal_moves=True,
    move_output_mode="index",
    legal_moves_format="comma",
    history_format="san",
    board_style="compact",
    strict_output_mode=True,
    max_history_moves=4,
    retry_tone="strict",
    output_reminder=(
        "Return only the option number from the legal move list.\n"
        "Do not write SAN, algebraic notation, or UCI move text.\n"
        "Valid examples: 1, 7, 12."
    ),
)


PROMPT_PROFILES = {
    DEFAULT_STRICT.name: DEFAULT_STRICT,
    COMPACT_HARDLINE.name: COMPACT_HARDLINE,
    READABLE_BOARD.name: READABLE_BOARD,
    GEMMA_UCI_HARDLINE.name: GEMMA_UCI_HARDLINE,
}


def get_prompt_profile(name: str) -> PromptProfile:
    try:
        return PROMPT_PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown prompt profile: {name}") from exc


def recommend_prompt_profile(model_name: str) -> PromptProfile:
    lowered = model_name.lower()
    if lowered.startswith("gemma"):
        return GEMMA_UCI_HARDLINE
    return DEFAULT_STRICT

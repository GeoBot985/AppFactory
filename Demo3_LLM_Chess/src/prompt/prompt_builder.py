import chess
from src.prompt.prompt_profiles import PromptProfile


def build_legal_move_options(board: chess.Board) -> list[dict[str, object]]:
    return [
        {"index": index, "uci": move.uci()}
        for index, move in enumerate(board.legal_moves, start=1)
    ]


def _format_legal_moves(legal_moves: list[str], profile: PromptProfile) -> str:
    if profile.legal_moves_format == "space":
        return "Legal moves:\n" + " ".join(legal_moves)
    if profile.legal_moves_format == "lines":
        return "Legal moves:\n" + "\n".join(f"- {move}" for move in legal_moves)
    return "Legal moves:\n" + ", ".join(legal_moves)


def _format_index_legal_moves(legal_move_options: list[dict[str, object]]) -> str:
    formatted_options = [f"{option['index']}. {option['uci']}" for option in legal_move_options]
    return "Legal move options:\n" + "\n".join(formatted_options)


def _format_history(board: chess.Board, move_history: list[str], profile: PromptProfile) -> str:
    if not profile.include_move_history or profile.max_history_moves <= 0:
        return ""

    if profile.history_format == "uci":
        uci_history = [move.uci() for move in board.move_stack]
        recent_moves = uci_history[-profile.max_history_moves:]
    else:
        recent_moves = move_history[-profile.max_history_moves:]

    if not recent_moves:
        return "Recent moves:\nNone"
    return "Recent moves:\n" + ", ".join(recent_moves)


def _retry_prefix(retry_context: dict, profile: PromptProfile) -> str:
    failure_type = retry_context.get("failure_type", "invalid_format")
    previous_response = retry_context.get("previous_response")
    attempt = retry_context.get("attempt")
    max_attempts = retry_context.get("max_attempts")

    if profile.move_output_mode == "index":
        tone_map = {
            "neutral": "Your previous response was invalid. Please return one option number from the legal move list.",
            "firm": "Your previous response was invalid. Return exactly one valid option number from the legal move list.",
            "strict": "Your previous response was rejected. Return exactly one option number from the provided list. Any extra text will fail.",
        }
        header = tone_map.get(profile.retry_tone, tone_map["firm"])
        lines = [header, f"Failure type: {failure_type}."]
        if failure_type == "selection_out_of_range":
            lines.append("Your previous response used an option number that is not in the current legal move list.")
            lines.append("Choose one valid option number only.")
        elif failure_type == "extra_text_detected":
            lines.append("Your previous response included extra text.")
            lines.append("Return only the number.")
        elif failure_type in {"invalid_selection_format", "parse_failed"}:
            lines.append("Your previous response did not match the required option-number format.")
            lines.append("Do not return move text, SAN, UCI, or prose.")
        elif failure_type == "resolved_move_illegal":
            lines.append("The selected option did not resolve to a legal move in the current position.")
            lines.append("Choose a valid option number from the current list.")
    else:
        tone_map = {
            "neutral": "Your previous response was invalid. Please return one legal UCI move.",
            "firm": "Your previous response was invalid or illegal. Choose only from the listed legal moves.",
            "strict": "Your previous response was rejected. Return exactly one legal UCI move from the provided list. Any extra text will fail.",
        }
        header = tone_map.get(profile.retry_tone, tone_map["firm"])

        lines = [header, f"Failure type: {failure_type}."]
        if failure_type == "illegal_move":
            lines.append("Your previous move is illegal in this exact position.")
            lines.append("It is not a valid choice from the legal move list.")
            lines.append("Do not repeat the previous move.")
        elif failure_type in {"no_uci_found", "invalid_format", "parse_failed"}:
            lines.append("Your previous response did not match the required UCI move format.")
            lines.append("Do not use SAN, prose, shorthand, or partial square names.")
    if attempt and max_attempts:
        lines.append(f"Retry attempt {attempt} of {max_attempts}.")
    if previous_response:
        lines.append(f"Previous response: {previous_response}")
    return "\n".join(lines)


def build_prompt(
    board: chess.Board,
    move_history: list[str],
    side: str,
    profile: PromptProfile,
    custom_instructions: str = "",
    retry_context=None,
    legal_move_options: list[dict[str, object]] | None = None,
) -> str:
    sections = []
    strategy_block = (
        "Play the strongest legal move you can find in the current position.\n"
        "Prioritize checkmate, material gain, tactical threats, and king safety.\n"
        "Protect your pieces by keeping them covered by other pieces whenever practical.\n"
        "Only enter trades, captures, or tactical sequences when the resulting position is favorable for you.\n"
        "Avoid obvious blunders, hanging pieces, and one-move losses."
    )
    if profile.move_output_mode == "index":
        side_block = (
            f"The side to move is {side}.\n"
            f"Move only the {side} pieces.\n"
            "Choose exactly one option number from the legal move list shown below.\n"
            "Your final answer must be exactly one valid option number from that list."
        )
    else:
        side_block = (
            f"The side to move is {side}.\n"
            f"Move only the {side} pieces.\n"
            "Choose exactly one move from the legal move list shown below.\n"
            "Your final answer must exactly match one legal move string from that list."
        )

    if retry_context:
        sections.append(_retry_prefix(retry_context, profile))

    if profile.board_style == "full":
        sections.append(f"You are playing chess as {side}. Choose the best legal move for the current position.")
    else:
        sections.append(f"You are playing as {side}.")

    sections.append(strategy_block)
    sections.append(side_block)

    if profile.include_fen:
        sections.append(f"Current FEN:\n{board.fen()}")

    if profile.include_ascii_board:
        label = "Board position:" if profile.board_style == "full" else "Board:"
        sections.append(f"{label}\n{board}")

    history_block = _format_history(board, move_history, profile)
    if history_block:
        sections.append(history_block)

    if profile.include_legal_moves:
        if legal_move_options is None:
            legal_move_options = build_legal_move_options(board)
        if profile.move_output_mode == "index":
            sections.append(_format_index_legal_moves(legal_move_options))
        else:
            legal_moves = [option["uci"] for option in legal_move_options]
            sections.append(_format_legal_moves(legal_moves, profile))

    if profile.strict_output_mode:
        if profile.move_output_mode == "index":
            sections.append("Any response that is not a single option number will be rejected.")
        else:
            sections.append("Any response that is not a single UCI move will be rejected.")

    if profile.output_reminder:
        sections.append(profile.output_reminder)

    if custom_instructions:
        sections.append(custom_instructions)

    if profile.move_output_mode == "index":
        sections.append(
            "Return only the option number.\n"
            "Example valid outputs:\n"
            "1\n"
            "3\n"
            "12\n"
            "Do not write the move text.\n"
            "Do not write UCI notation.\n"
            "Do not explain.\n"
            "Do not include any other text.\n"
            "Return only the option number."
        )
    else:
        sections.append(
            "Return exactly one legal move in UCI format.\n"
            "Examples: e2e4, g1f3, e7e8q\n"
            "Copy one legal move exactly as written in the legal moves list.\n"
            "Do not explain.\n"
            "Do not include any other text.\n"
            "Return only the move."
        )

    return "\n\n".join(section for section in sections if section)

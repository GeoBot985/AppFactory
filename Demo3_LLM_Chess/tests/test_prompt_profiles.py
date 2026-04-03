import os
import sys
import unittest
from dataclasses import replace

import chess

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.prompt.prompt_builder import build_prompt
from src.prompt.prompt_profiles import COMPACT_HARDLINE, DEFAULT_STRICT, GEMMA_UCI_HARDLINE, READABLE_BOARD
from src.prompt.model_prompt_registry import get_model_prompt_settings


LEGACY_UCI_PROFILE = replace(DEFAULT_STRICT, name="LEGACY_UCI_PROFILE", move_output_mode="uci")


class TestPromptProfiles(unittest.TestCase):
    def setUp(self):
        self.board = chess.Board()
        self.move_history = ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6"]

    def test_default_profile_builds_valid_prompt(self):
        prompt = build_prompt(self.board, self.move_history, "white", DEFAULT_STRICT)

        self.assertIn("You are playing as white.", prompt)
        self.assertIn("Play the strongest legal move you can find in the current position.", prompt)
        self.assertIn("Protect your pieces by keeping them covered by other pieces whenever practical.", prompt)
        self.assertIn("Only enter trades, captures, or tactical sequences when the resulting position is favorable for you.", prompt)
        self.assertIn("The side to move is white.", prompt)
        self.assertIn("Choose exactly one option number from the legal move list shown below.", prompt)
        self.assertIn("Your final answer must be exactly one valid option number from that list.", prompt)
        self.assertIn("Current FEN:", prompt)
        self.assertIn("Legal move options:\n1. ", prompt)
        self.assertIn("Return only the option number.", prompt)
        self.assertNotIn("Return exactly one legal move in UCI format.", prompt)

    def test_compact_profile_omits_optional_sections(self):
        prompt = build_prompt(self.board, self.move_history, "white", COMPACT_HARDLINE)

        self.assertNotIn("Board:\n", prompt)
        self.assertNotIn("Recent moves:", prompt)

    def test_readable_board_profile_uses_numbered_legal_moves(self):
        prompt = build_prompt(self.board, self.move_history, "black", READABLE_BOARD)

        self.assertIn("Legal move options:\n1. ", prompt)
        self.assertIn("Do not write the move text.", prompt)

    def test_retry_context_changes_prompt(self):
        prompt = build_prompt(
            self.board,
            self.move_history,
            "white",
            DEFAULT_STRICT,
            retry_context={
                "attempt": 2,
                "max_attempts": 3,
                "failure_type": "illegal_move",
                "previous_response": "e1e3",
            },
        )

        self.assertIn("Failure type: illegal_move.", prompt)
        self.assertIn("Retry attempt 2 of 3.", prompt)
        self.assertIn("Previous response: e1e3", prompt)

    def test_index_mode_retry_context_uses_selection_language(self):
        prompt = build_prompt(
            self.board,
            self.move_history,
            "white",
            DEFAULT_STRICT,
            retry_context={
                "attempt": 2,
                "max_attempts": 3,
                "failure_type": "selection_out_of_range",
                "previous_response": "99",
            },
        )

        self.assertIn("Failure type: selection_out_of_range.", prompt)
        self.assertIn("Choose one valid option number only.", prompt)
        self.assertIn("Previous response: 99", prompt)

    def test_strict_output_mode_adds_hardening(self):
        prompt = build_prompt(self.board, self.move_history, "white", DEFAULT_STRICT)

        self.assertIn("Any response that is not a single option number will be rejected.", prompt)

    def test_max_history_truncation_works(self):
        prompt = build_prompt(self.board, self.move_history, "white", DEFAULT_STRICT)

        self.assertIn("Nf3, Nc6, Bb5, a6, Ba4, Nf6", prompt)
        self.assertNotIn("e4, e5, Nf3", prompt)

    def test_gemma_profile_adds_index_only_warning(self):
        prompt = build_prompt(self.board, self.move_history, "black", GEMMA_UCI_HARDLINE)

        self.assertIn("Return only the option number from the legal move list.", prompt)
        self.assertIn("Do not write SAN, algebraic notation, or UCI move text.", prompt)

    def test_model_specific_custom_instructions_are_included(self):
        settings = get_model_prompt_settings("gemma3:4b")
        prompt = build_prompt(
            self.board,
            self.move_history,
            "black",
            settings.profile,
            custom_instructions=settings.custom_instructions,
        )

        self.assertIn("Choose one option number only.", prompt)
        self.assertIn("Do not answer with SAN captures such as Qxd8+ or exd6.", prompt)
        self.assertIn("If an undefended enemy piece can be captured safely in one move, prefer that capture.", prompt)

    def test_legacy_uci_mode_still_uses_uci_contract(self):
        prompt = build_prompt(self.board, self.move_history, "white", LEGACY_UCI_PROFILE)

        self.assertIn("Choose exactly one move from the legal move list shown below.", prompt)
        self.assertIn("Legal moves:", prompt)
        self.assertIn("Return exactly one legal move in UCI format.", prompt)


if __name__ == "__main__":
    unittest.main()

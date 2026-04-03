import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import chess
import threading
from dataclasses import replace

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.controller.game_controller import GameController, GameState
from src.llm.player import LLMPlayer
from src.llm.ollama_adapter import MoveParseError
from src.prompt.prompt_profiles import DEFAULT_STRICT
from src.prompt.prompt_builder import build_legal_move_options

LEGACY_UCI_PROFILE = replace(DEFAULT_STRICT, name="LEGACY_UCI_PROFILE", move_output_mode="uci")

class TestGameController(unittest.TestCase):
    def _move_index_for(self, board: chess.Board, uci_move: str) -> str:
        for option in build_legal_move_options(board):
            if option["uci"] == uci_move:
                return str(option["index"])
        self.fail(f"Move {uci_move} not found in legal options")

    def _board_after_moves(self, *moves: str) -> chess.Board:
        board = chess.Board()
        for move in moves:
            board.push_uci(move)
        return board


    def setUp(self):
        # Mock players and adapters
        self.white_adapter = MagicMock()
        self.black_adapter = MagicMock()
        self.white_player = LLMPlayer("white_model", "white", self.white_adapter, DEFAULT_STRICT)
        self.black_player = LLMPlayer("black_model", "black", self.black_adapter, DEFAULT_STRICT)

        # Mock GUI
        self.gui = MagicMock()
        # The GUI's after method needs to be handled for threaded tests
        self.gui.after = MagicMock(side_effect=lambda ms, func, *args: func(*args))
        
        # Controller
        self.controller = GameController(self.white_player, self.black_player)
        self.controller.set_gui(self.gui)
        self.controller.board.reset() # Ensure clean board

    def test_single_turn_execution(self):
        self.white_adapter.get_response.return_value = self._move_index_for(self.controller.board, "e2e4")
        
        self.controller.execute_single_turn()

        # Last move on stack should be e4
        self.assertEqual(self.controller.board.move_stack[-1].uci(), "e2e4")
        self.assertEqual(len(self.controller.move_history), 1)
        # Check that the board view was updated
        self.gui.board_view.update_board.assert_called_with(self.controller.board)

    def test_invalid_then_valid_selection(self):
        self.white_adapter.get_response.side_effect = [
            "abc",
            "99",
            self._move_index_for(self.controller.board, "e2e4"),
        ]
        
        self.controller.execute_single_turn()

        self.assertEqual(self.controller.board.move_stack[-1].uci(), "e2e4")
        self.assertEqual(self.white_adapter.get_response.call_count, 3)

    def test_legacy_uci_mode_still_parses_san_response(self):
        self.white_player.prompt_profile = LEGACY_UCI_PROFILE
        self.white_adapter.get_move.side_effect = MoveParseError(
            "No valid UCI move found in model response",
            raw_response="e4",
        )

        self.controller.execute_single_turn()

        self.assertEqual(self.controller.board.move_stack[-1].uci(), "e2e4")

    def test_legacy_uci_mode_parses_black_san_response(self):
        self.white_player.prompt_profile = LEGACY_UCI_PROFILE
        self.black_player.prompt_profile = LEGACY_UCI_PROFILE
        self.white_adapter.get_move.return_value = {"raw": "e2e4", "parsed": "e2e4"}
        self.black_adapter.get_move.side_effect = MoveParseError(
            "No valid UCI move found in model response",
            raw_response="d6",
        )

        self.controller.execute_single_turn()
        self.controller.execute_single_turn()

        self.assertEqual(self.controller.board.peek().uci(), "d7d6")

    def test_unique_square_helper_resolves_single_legal_match(self):
        self.controller.board.reset()
        move = self.controller._try_parse_unique_square_response("e4")
        self.assertIsNotNone(move)
        self.assertEqual(move.uci(), "e2e4")

    def test_set_player_model_updates_profile_recommendation(self):
        self.controller.set_player_model("black", "gemma3:1b")
        self.assertEqual(self.black_player.prompt_profile.name, "GEMMA_UCI_HARDLINE")
        self.assertIn("Return only the number of the chosen option.", self.black_player.prompt_instructions)

    def test_piece_square_helper_resolves_unique_legal_move(self):
        self.controller.board = chess.Board("r1bqkb1r/ppp2p1N/3p3P/4p3/1n5P/8/PPPPPP2/RNBQKB1R b KQkq - 0 7")
        move = self.controller._try_parse_piece_square_response("Bd7")
        self.assertIsNotNone(move)
        self.assertEqual(move.uci(), "c8d7")

    def test_all_retries_fail(self):
        self.white_adapter.get_response.side_effect = ["bad"] * 3
        
        self.controller.execute_single_turn()

        self.assertEqual(self.controller.state, GameState.ERROR)
        self.gui.update_status.assert_called_with("Error: white_model forfeits.")

    def test_alternating_turns(self):
        self.controller.board.reset()
        self.white_adapter.get_response.return_value = self._move_index_for(self.controller.board, "e2e4")
        self.controller.execute_single_turn() # White's turn
        self.assertEqual(self.controller.board.peek().uci(), "e2e4")

        self.black_adapter.get_response.return_value = self._move_index_for(self.controller.board, "e7e5")
        
        self.controller.execute_single_turn() # Black's turn
        self.assertEqual(self.controller.board.peek().uci(), "e7e5")
        
        self.assertEqual(len(self.controller.move_history), 2)

    def test_set_player_model_updates_player_and_adapter(self):
        self.controller.set_player_model("white", "new_white_model")
        self.assertEqual(self.white_player.name, "new_white_model")
        self.assertEqual(self.white_adapter.model_name, "new_white_model")
        self.gui.update_model_names.assert_called_with("new_white_model", "black_model")

    @patch('src.controller.game_controller.time.sleep', return_value=None) # Don't sleep in tests
    def test_game_over_detection_in_loop(self, patched_time_sleep):
        # Fool's mate
        self.controller.board.reset()
        self.white_adapter.get_response.side_effect = [
            self._move_index_for(self.controller.board, "f2f3"),
            self._move_index_for(self._board_after_moves("f2f3", "e7e5"), "g2g4"),
        ]
        self.black_adapter.get_response.side_effect = [
            self._move_index_for(self._board_after_moves("f2f3"), "e7e5"),
            self._move_index_for(self._board_after_moves("f2f3", "e7e5", "g2g4"), "d8h4"),
        ]
        
        # Start the game loop in a thread
        self.controller.state = GameState.RUNNING
        game_thread = threading.Thread(target=self.controller.play_game_loop)
        game_thread.start()
        
        # Give the thread time to run and finish
        game_thread.join(timeout=2)

        self.assertTrue(self.controller.board.is_checkmate())
        self.assertEqual(self.controller.state, GameState.FINISHED)
        self.gui.update_status.assert_called_with("Finished: Black wins by checkmate.")

    def test_out_of_range_index_triggers_retry(self):
        self.white_adapter.get_response.side_effect = ["99", self._move_index_for(self.controller.board, "e2e4")]

        self.controller.execute_single_turn()

        self.assertEqual(self.controller.board.peek().uci(), "e2e4")
        self.assertEqual(self.white_adapter.get_response.call_count, 2)

    def test_repeated_bad_selection_forfeits_after_retry_limit(self):
        self.white_adapter.get_response.side_effect = ["bad"] * 5

        self.controller.execute_single_turn()

        self.assertEqual(self.controller.state, GameState.ERROR)

    def test_valid_selection_updates_board_with_exact_resolved_move(self):
        self.white_adapter.get_response.return_value = self._move_index_for(self.controller.board, "g1f3")

        self.controller.execute_single_turn()

        self.assertEqual(self.controller.board.peek().uci(), "g1f3")


if __name__ == '__main__':
    unittest.main()

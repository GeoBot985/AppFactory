import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import json
import time
import chess

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.logging.turn_logger import TurnLogger
from src.controller.game_controller import GameController
from src.llm.player import LLMPlayer
from src.prompt.prompt_profiles import DEFAULT_STRICT
from src.prompt.prompt_builder import build_legal_move_options

class TestLogging(unittest.TestCase):
    def _move_index_for(self, board: chess.Board, uci_move: str) -> str:
        for option in build_legal_move_options(board):
            if option["uci"] == uci_move:
                return str(option["index"])
        self.fail(f"Move {uci_move} not found in legal options")


    def setUp(self):
        self.log_path = "runtime/logs/test_log.jsonl"
        # Clean up any old log files
        if os.path.exists(self.log_path):
            os.remove(self.log_path)
            
        # Mock players and controller for logging tests
        self.white_adapter = MagicMock()
        self.black_adapter = MagicMock()
        self.white_player = LLMPlayer("test_white_model", "white", self.white_adapter, DEFAULT_STRICT)
        self.black_player = LLMPlayer("test_black_model", "black", self.black_adapter, DEFAULT_STRICT)
        
        self.controller = GameController(self.white_player, self.black_player)
        # We are testing the logger via the controller, so we need to set it up
        self.controller.logger = TurnLogger(self.log_path)
        
        self.gui = MagicMock()
        self.gui.after = MagicMock(side_effect=lambda ms, func, *args: func(*args))
        self.controller.set_gui(self.gui)


    def tearDown(self):
        if os.path.exists(self.log_path):
            os.remove(self.log_path)

    def test_log_file_created(self):
        self.white_adapter.get_response.return_value = self._move_index_for(self.controller.board, "e2e4")
        self.controller.execute_single_turn()
        self.assertTrue(os.path.exists(self.log_path))

    def test_valid_turn_logged(self):
        self.white_adapter.get_response.return_value = self._move_index_for(self.controller.board, "e2e4")
        self.controller.execute_single_turn()
        
        with open(self.log_path, 'r') as f:
            log_entry = json.loads(f.readline())
            
        self.assertEqual(log_entry['move_number'], 1)
        self.assertEqual(log_entry['side'], 'white')
        self.assertEqual(log_entry['model'], 'test_white_model')
        self.assertEqual(log_entry['prompt_profile'], 'DEFAULT_STRICT')
        self.assertEqual(log_entry['move_output_mode'], 'index')
        self.assertEqual(log_entry['legal_moves_format'], 'comma')
        self.assertEqual(log_entry['retry_tone'], 'firm')
        self.assertIn('timestamp', log_entry)
        self.assertEqual(log_entry['raw_response'], self._move_index_for(chess.Board(), 'e2e4'))
        self.assertEqual(log_entry['parsed_index'], int(self._move_index_for(chess.Board(), 'e2e4')))
        self.assertEqual(log_entry['parsed_move'], 'e2e4')
        self.assertEqual(log_entry['resolved_move'], 'e2e4')
        self.assertTrue(log_entry['legal'])
        self.assertEqual(log_entry['watcher_decision'], 'allow')
        self.assertEqual(log_entry['watcher_reason_code'], 'ok')
        self.assertEqual(log_entry['attempts'][-1]['parsed_move'], 'e2e4')
        self.assertTrue(log_entry['result'], 'move_applied')

    def test_retry_attempts_recorded(self):
        self.white_adapter.get_response.side_effect = [
            "bad",
            self._move_index_for(self.controller.board, "e2e4")
        ]
        self.controller.execute_single_turn()
        
        with open(self.log_path, 'r') as f:
            log_entry = json.loads(f.readline())
            
        self.assertEqual(log_entry['retries'], 1)
        self.assertEqual(len(log_entry['attempts']), 2)
        self.assertEqual(log_entry['attempts'][0]['error'], 'invalid_selection_format')
        self.assertEqual(log_entry['attempts'][0]['watcher_reason_code'], 'invalid_selection_format')
        self.assertIsNone(log_entry['attempts'][1]['error'])

    def test_duration_recorded(self):
        # Add a small delay to ensure duration is non-zero
        def delayed_get_response(*args, **kwargs):
            time.sleep(0.01)
            return self._move_index_for(self.controller.board, "e2e4")
        self.white_adapter.get_response.side_effect = delayed_get_response

        self.controller.execute_single_turn()
        
        with open(self.log_path, 'r') as f:
            log_entry = json.loads(f.readline())
            
        self.assertIn('duration_ms', log_entry)
        self.assertGreater(log_entry['duration_ms'], 0)

    @patch('src.logging.turn_logger.open')
    def test_logging_failure_safe(self, mock_open):
        mock_open.side_effect = IOError("Disk full")
        self.white_adapter.get_response.return_value = self._move_index_for(self.controller.board, "e2e4")
        
        # This should not raise an exception
        with patch('builtins.print') as mock_print:
            self.controller.execute_single_turn()
            mock_print.assert_called_with("Error writing to log file: Disk full")
        
        # And the game should proceed
        self.assertEqual(self.controller.board.move_stack[-1].uci(), "e2e4")


if __name__ == '__main__':
    unittest.main()

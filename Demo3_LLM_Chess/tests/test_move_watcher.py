import os
import sys
import unittest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.watcher.move_watcher import MoveWatcher


class TestMoveWatcher(unittest.TestCase):
    def setUp(self):
        self.watcher = MoveWatcher()

    def _context(self, **overrides):
        context = {
            "side": "white",
            "model_name": "qwen2.5:3b",
            "move_number": 5,
            "fen": "test-fen",
            "raw_response": "12",
            "parsed_index": 12,
            "parsed_move": "e2e4",
            "parse_error": None,
            "is_legal": True,
            "attempt": 1,
            "max_attempts": 3,
            "prompt_profile": "DEFAULT_STRICT",
            "move_output_mode": "index",
            "prior_attempts": [],
        }
        context.update(overrides)
        return context

    def test_legal_clean_move_allowed(self):
        result = self.watcher.inspect(self._context())
        self.assertEqual(result["decision"], "allow")
        self.assertEqual(result["reason_code"], "ok")

    def test_legal_selection_with_extra_text_allowed_but_flagged(self):
        result = self.watcher.inspect(self._context(raw_response="I choose 12"))
        self.assertEqual(result["decision"], "allow")
        self.assertEqual(result["reason_code"], "extra_text_detected")

    def test_selection_format_failure_retries_before_max(self):
        result = self.watcher.inspect(
            self._context(raw_response="Move pawn", parsed_index=None, parsed_move=None, parse_error="invalid_selection_format", is_legal=False)
        )
        self.assertEqual(result["decision"], "retry")
        self.assertEqual(result["reason_code"], "invalid_selection_format")

    def test_parse_failure_forfeits_at_max(self):
        result = self.watcher.inspect(
            self._context(raw_response="Move pawn", parsed_index=None, parsed_move=None, parse_error="invalid_selection_format", is_legal=False, attempt=3)
        )
        self.assertEqual(result["decision"], "forfeit")
        self.assertEqual(result["reason_code"], "retry_limit_reached")

    def test_out_of_range_selection_retries_before_max(self):
        result = self.watcher.inspect(
            self._context(raw_response="99", parsed_index=99, parsed_move=None, is_legal=False, parse_error="selection_out_of_range", attempt=2)
        )
        self.assertEqual(result["decision"], "retry")
        self.assertEqual(result["reason_code"], "selection_out_of_range")

    def test_repeated_identical_invalid_response_flagged(self):
        result = self.watcher.inspect(
            self._context(
                raw_response="Move pawn",
                parsed_index=None,
                parsed_move=None,
                parse_error="invalid_selection_format",
                is_legal=False,
                attempt=2,
                prior_attempts=[{"raw_response": "Move pawn", "parsed_index": None, "parsed_move": None, "reason_code": "invalid_selection_format"}],
            )
        )
        self.assertEqual(result["decision"], "retry")
        self.assertEqual(result["reason_code"], "repeated_invalid_response")

    def test_timeout_handled_deterministically(self):
        result = self.watcher.inspect(
            self._context(raw_response="timeout", parsed_move=None, parse_error="timeout", is_legal=False, attempt=2)
        )
        self.assertEqual(result["decision"], "retry")
        self.assertEqual(result["reason_code"], "timeout")

    def test_legacy_uci_mode_still_works(self):
        result = self.watcher.inspect(
            self._context(raw_response="e2e4", parsed_index=None, parsed_move="e2e4", move_output_mode="uci")
        )
        self.assertEqual(result["decision"], "allow")
        self.assertEqual(result["reason_code"], "ok")


if __name__ == "__main__":
    unittest.main()

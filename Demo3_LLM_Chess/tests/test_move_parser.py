import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.llm.move_parser import parse_move_selection


class TestMoveParser(unittest.TestCase):
    def test_bare_integer_parses_as_index(self):
        parsed = parse_move_selection("12")
        self.assertEqual(parsed["parsed_index"], 12)

    def test_prefixed_integer_parses_as_index(self):
        parsed = parse_move_selection(" MOVE_INDEX: 7 ")
        self.assertEqual(parsed["parsed_index"], 7)

    def test_uci_move_fails_in_index_mode(self):
        with self.assertRaises(ValueError):
            parse_move_selection("e2e4")

    def test_option_phrase_fails_in_index_mode(self):
        with self.assertRaises(ValueError):
            parse_move_selection("option 3")

    def test_extra_text_fails_in_index_mode(self):
        with self.assertRaises(ValueError):
            parse_move_selection("3 because it wins")


if __name__ == "__main__":
    unittest.main()

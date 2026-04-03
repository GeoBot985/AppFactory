import unittest
import tkinter as tk
import sys
import os
import chess

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.gui.main_window import MainWindow

class TestGuiSmoke(unittest.TestCase):

    def setUp(self):
        # This is not ideal, but for a smoke test it's okay to create a root window.
        # For more complex tests, this should be mocked.
        try:
            self.app = MainWindow()
            self.app.update()
        except tk.TclError:
            # This can happen in environments without a display
            self.skipTest("Could not create a Tkinter window.")


    def tearDown(self):
        if self.app:
            self.app.destroy()

    def test_window_creation(self):
        self.assertIsNotNone(self.app)
        self.assertEqual(self.app.title(), "LLM Chess")

    def test_board_view_initial_position(self):
        board = chess.Board()
        self.app.board_view.update_board(board)
        # A simple check: count the number of pieces.
        self.assertEqual(len(self.app.board_view.find_withtag("pieces")), 32)
        self.assertEqual(len(self.app.board_view.find_withtag("legend")), 16)

    def test_move_log_updates(self):
        self.app.move_log_view.add_move("e4", 1, "white")
        content = self.app.move_log_view.get("1.0", tk.END).strip()
        self.assertEqual(content, "1. e4")

    def test_status_panel_updates(self):
        self.app.update_status("Test Status")
        self.assertEqual(self.app.control_panel.status_label.cget("text"), "Status: Test Status")

        self.app.update_turn("Black")
        self.assertEqual(self.app.control_panel.turn_label.cget("text"), "Turn: Black")

        self.app.update_model_names("test_white", "test_black")
        self.assertEqual(self.app.control_panel.white_model_label.cget("text"), "White: test_white")
        self.assertEqual(self.app.control_panel.black_model_label.cget("text"), "Black: test_black")
        self.assertEqual(self.app.control_panel.white_model_var.get(), "test_white")
        self.assertEqual(self.app.control_panel.black_model_var.get(), "test_black")

    def test_model_selectors_accept_available_models(self):
        self.app.set_available_models(["qwen2.5:3b", "llama3.2:3b"])
        self.assertEqual(
            tuple(self.app.control_panel.white_model_selector.cget("values")),
            ("qwen2.5:3b", "llama3.2:3b"),
        )
        self.app.update_model_names("qwen2.5:3b", "llama3.2:3b")
        self.assertEqual(self.app.control_panel.white_model_var.get(), "qwen2.5:3b")

if __name__ == '__main__':
    unittest.main()

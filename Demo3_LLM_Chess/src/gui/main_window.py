import tkinter as tk
from tkinter import ttk

from src.gui.board_view import BoardView
from src.gui.control_panel import ControlPanel
from src.gui.move_log_view import MoveLogView
from src.gui.debug_panel import DebugPanel
from src.config import ENABLE_DEBUG_PANEL

class MainWindow(tk.Tk):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title("LLM Chess")
        self.geometry("1000x750") # Increased height for debug panel

        # Main frame
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill="both", expand=True)

        # Board view
        self.board_view = BoardView(self.main_frame)
        self.board_view.pack(side="left", fill="both", expand=True)

        # Right panel
        self.right_panel = ttk.Frame(self.main_frame)
        self.right_panel.pack(side="right", fill="y", padx=5, pady=5)
        
        # Control panel
        self.control_panel = ControlPanel(self.right_panel)
        self.control_panel.pack(fill="x")

        # Move log
        self.move_log_view = MoveLogView(self.right_panel, height=10)
        self.move_log_view.pack(fill="both", expand=True, pady=5)
        
        # Debug panel
        if ENABLE_DEBUG_PANEL:
            self.debug_panel = DebugPanel(self.right_panel)
            self.debug_panel.pack(fill="x", pady=5)
        
    def set_controller(self, controller):
        self.controller = controller
        self.control_panel.start_button.config(command=self.controller.start_game)
        self.control_panel.pause_button.config(command=self.controller.pause_game)
        self.control_panel.resume_button.config(command=self.controller.resume_game)
        self.control_panel.reset_button.config(command=self.controller.reset_game)
        self.control_panel.step_button.config(command=self.controller.step_turn)
        self.control_panel.white_model_selector.bind("<<ComboboxSelected>>", self._on_white_model_selected)
        self.control_panel.black_model_selector.bind("<<ComboboxSelected>>", self._on_black_model_selected)
        
    def update_status(self, text):
        self.control_panel.status_label.config(text=f"Status: {text}")

    def update_turn(self, side):
        self.control_panel.turn_label.config(text=f"Turn: {side}")
        
    def update_model_names(self, white_name, black_name):
        self.control_panel.white_model_label.config(text=f"White: {white_name}")
        self.control_panel.black_model_label.config(text=f"Black: {black_name}")
        self.control_panel.set_selected_models(white_name, black_name)

    def set_available_models(self, model_names):
        self.control_panel.set_available_models(model_names)

    def update_debug_panel(self, debug_data):
        if ENABLE_DEBUG_PANEL and hasattr(self, 'debug_panel'):
            self.debug_panel.update_panel(debug_data)
            
    def clear_debug_panel(self):
        if ENABLE_DEBUG_PANEL and hasattr(self, 'debug_panel'):
            self.debug_panel.clear_panel()

    def _on_white_model_selected(self, _event):
        if hasattr(self, "controller"):
            self.controller.set_player_model("white", self.control_panel.white_model_var.get())

    def _on_black_model_selected(self, _event):
        if hasattr(self, "controller"):
            self.controller.set_player_model("black", self.control_panel.black_model_var.get())

import tkinter as tk
from tkinter import ttk

class DebugPanel(ttk.LabelFrame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, text="Debug Info", *args, **kwargs)

        self.model_label = ttk.Label(self, text="Model: ")
        self.model_label.pack(anchor="w", padx=5, pady=2)

        self.profile_label = ttk.Label(self, text="Profile: ")
        self.profile_label.pack(anchor="w", padx=5, pady=2)

        self.turn_label = ttk.Label(self, text="Move: ")
        self.turn_label.pack(anchor="w", padx=5, pady=2)
        
        self.raw_response_label = ttk.Label(self, text="Raw Response:")
        self.raw_response_label.pack(anchor="w", padx=5, pady=2)
        self.raw_response_text = tk.Text(self, height=5, state=tk.DISABLED)
        self.raw_response_text.pack(fill="x", padx=5, pady=2)

        self.prompt_label = ttk.Label(self, text="Prompt Preview:")
        self.prompt_label.pack(anchor="w", padx=5, pady=2)
        self.prompt_preview_label = ttk.Label(self, text="", wraplength=280, justify="left")
        self.prompt_preview_label.pack(anchor="w", fill="x", padx=5, pady=2)

        self.parsed_index_label = ttk.Label(self, text="Parsed Index: ")
        self.parsed_index_label.pack(anchor="w", padx=5, pady=2)

        self.parsed_move_label = ttk.Label(self, text="Parsed Move: ")
        self.parsed_move_label.pack(anchor="w", padx=5, pady=2)

        self.resolved_move_label = ttk.Label(self, text="Resolved Move: ")
        self.resolved_move_label.pack(anchor="w", padx=5, pady=2)

        self.status_label = ttk.Label(self, text="Status: ")
        self.status_label.pack(anchor="w", padx=5, pady=2)

        self.error_label = ttk.Label(self, text="Error: ")
        self.error_label.pack(anchor="w", padx=5, pady=2)

        self.watcher_decision_label = ttk.Label(self, text="Watcher Decision: ")
        self.watcher_decision_label.pack(anchor="w", padx=5, pady=2)

        self.watcher_reason_label = ttk.Label(self, text="Watcher Reason: ")
        self.watcher_reason_label.pack(anchor="w", padx=5, pady=2)

        self.watcher_message_label = ttk.Label(self, text="Watcher Message: ", wraplength=280, justify="left")
        self.watcher_message_label.pack(anchor="w", fill="x", padx=5, pady=2)

        self.attempts_label = ttk.Label(self, text="Attempts: ")
        self.attempts_label.pack(anchor="w", padx=5, pady=2)

        self.time_label = ttk.Label(self, text="Time: ")
        self.time_label.pack(anchor="w", padx=5, pady=2)

    def update_panel(self, debug_data):
        self.model_label.config(text=f"Model: {debug_data.get('model', 'N/A')}")
        self.profile_label.config(text=f"Profile: {debug_data.get('prompt_profile', 'N/A')}")
        self.turn_label.config(text=f"Move: {debug_data.get('move_number', 'N/A')} ({debug_data.get('side', 'N/A')})")
        
        self.raw_response_text.config(state=tk.NORMAL)
        self.raw_response_text.delete("1.0", tk.END)
        self.raw_response_text.insert("1.0", debug_data.get('raw_response', 'N/A'))
        self.raw_response_text.config(state=tk.DISABLED)

        self.prompt_preview_label.config(text=debug_data.get("prompt_preview", ""))
        self.parsed_index_label.config(text=f"Parsed Index: {debug_data.get('parsed_index', 'N/A')}")
        self.parsed_move_label.config(text=f"Parsed Move: {debug_data.get('parsed_move', 'N/A')}")
        self.resolved_move_label.config(text=f"Resolved Move: {debug_data.get('resolved_move', 'N/A')}")
        self.status_label.config(text=f"Status: {debug_data.get('validity', 'N/A')}")
        self.error_label.config(text=f"Error: {debug_data.get('error', 'None')}")
        self.watcher_decision_label.config(text=f"Watcher Decision: {debug_data.get('watcher_decision', 'N/A')}")
        self.watcher_reason_label.config(text=f"Watcher Reason: {debug_data.get('watcher_reason_code', 'N/A')}")
        self.watcher_message_label.config(text=f"Watcher Message: {debug_data.get('watcher_message', 'N/A')}")
        self.attempts_label.config(text=f"Attempts: {debug_data.get('attempt', 'N/A')} / {debug_data.get('max_attempts', 'N/A')}")
        self.time_label.config(text=f"Time: {debug_data.get('duration_ms', 'N/A')} ms")

    def clear_panel(self):
        self.model_label.config(text="Model: ")
        self.profile_label.config(text="Profile: ")
        self.turn_label.config(text="Move: ")
        
        self.raw_response_text.config(state=tk.NORMAL)
        self.raw_response_text.delete("1.0", tk.END)
        self.raw_response_text.config(state=tk.DISABLED)

        self.prompt_preview_label.config(text="")
        self.parsed_index_label.config(text="Parsed Index: ")
        self.parsed_move_label.config(text="Parsed Move: ")
        self.resolved_move_label.config(text="Resolved Move: ")
        self.status_label.config(text="Status: ")
        self.error_label.config(text="Error: ")
        self.watcher_decision_label.config(text="Watcher Decision: ")
        self.watcher_reason_label.config(text="Watcher Reason: ")
        self.watcher_message_label.config(text="Watcher Message: ")
        self.attempts_label.config(text="Attempts: ")
        self.time_label.config(text="Time: ")

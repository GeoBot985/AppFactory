import tkinter as tk
from tkinter import ttk

class ControlPanel(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.white_model_var = tk.StringVar()
        self.black_model_var = tk.StringVar()
        
        # Match Info
        self.match_info_frame = ttk.LabelFrame(self, text="Match Info")
        self.match_info_frame.pack(fill="x", padx=5, pady=5)

        self.white_model_label = ttk.Label(self.match_info_frame, text="White: ")
        self.white_model_label.pack(anchor="w")
        self.white_model_selector = ttk.Combobox(
            self.match_info_frame,
            textvariable=self.white_model_var,
            state="readonly",
        )
        self.white_model_selector.pack(fill="x", pady=(0, 4))
        self.black_model_label = ttk.Label(self.match_info_frame, text="Black: ")
        self.black_model_label.pack(anchor="w")
        self.black_model_selector = ttk.Combobox(
            self.match_info_frame,
            textvariable=self.black_model_var,
            state="readonly",
        )
        self.black_model_selector.pack(fill="x", pady=(0, 4))
        self.turn_label = ttk.Label(self.match_info_frame, text="Turn: ")
        self.turn_label.pack(anchor="w")
        self.status_label = ttk.Label(self.match_info_frame, text="Status: Idle")
        self.status_label.pack(anchor="w")

        # Controls
        self.controls_frame = ttk.LabelFrame(self, text="Controls")
        self.controls_frame.pack(fill="x", padx=5, pady=5)

        self.start_button = ttk.Button(self.controls_frame, text="Start Match")
        self.start_button.pack(side="left", padx=5)
        self.pause_button = ttk.Button(self.controls_frame, text="Pause Match", state=tk.DISABLED)
        self.pause_button.pack(side="left", padx=5)
        self.resume_button = ttk.Button(self.controls_frame, text="Resume Match", state=tk.DISABLED)
        self.resume_button.pack(side="left", padx=5)
        self.reset_button = ttk.Button(self.controls_frame, text="Reset Match", state=tk.DISABLED)
        self.reset_button.pack(side="left", padx=5)
        self.step_button = ttk.Button(self.controls_frame, text="Step Turn")
        self.step_button.pack(side="left", padx=5)

        # Playback
        self.playback_frame = ttk.LabelFrame(self, text="Playback")
        self.playback_frame.pack(fill="x", padx=5, pady=5)
        
        self.delay_label = ttk.Label(self.playback_frame, text="Move Delay (s):")
        self.delay_label.pack(side="left", padx=5)
        self.delay_scale = ttk.Scale(self.playback_frame, from_=0.1, to=5.0, orient=tk.HORIZONTAL)
        self.delay_scale.set(1.0)
        self.delay_scale.pack(side="left", fill="x", expand=True)

        # Model Output
        self.model_output_frame = ttk.LabelFrame(self, text="Model Output")
        self.model_output_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.model_output_text = tk.Text(self.model_output_frame, height=10, state=tk.DISABLED)
        self.model_output_text.pack(fill="both", expand=True)
        
    def set_control_state(self, state):
        if state == "idle":
            self.start_button.config(state=tk.NORMAL)
            self.pause_button.config(state=tk.DISABLED)
            self.resume_button.config(state=tk.DISABLED)
            self.reset_button.config(state=tk.DISABLED)
            self.step_button.config(state=tk.NORMAL)
            self.set_model_selector_state("readonly")
        elif state == "running":
            self.start_button.config(state=tk.DISABLED)
            self.pause_button.config(state=tk.NORMAL)
            self.resume_button.config(state=tk.DISABLED)
            self.reset_button.config(state=tk.NORMAL)
            self.step_button.config(state=tk.DISABLED)
            self.set_model_selector_state(tk.DISABLED)
        elif state == "paused":
            self.start_button.config(state=tk.DISABLED)
            self.pause_button.config(state=tk.DISABLED)
            self.resume_button.config(state=tk.NORMAL)
            self.reset_button.config(state=tk.NORMAL)
            self.step_button.config(state=tk.NORMAL)
            self.set_model_selector_state("readonly")
        elif state == "finished" or state == "error":
            self.start_button.config(state=tk.DISABLED)
            self.pause_button.config(state=tk.DISABLED)
            self.resume_button.config(state=tk.DISABLED)
            self.reset_button.config(state=tk.NORMAL)
            self.step_button.config(state=tk.DISABLED)
            self.set_model_selector_state("readonly")

    def set_available_models(self, model_names):
        self.white_model_selector["values"] = model_names
        self.black_model_selector["values"] = model_names

    def set_selected_models(self, white_name, black_name):
        self.white_model_var.set(white_name)
        self.black_model_var.set(black_name)

    def set_model_selector_state(self, state):
        self.white_model_selector.config(state=state)
        self.black_model_selector.config(state=state)

    def update_model_output(self, model_name, raw_response, parsed_move, validity, retry_count):
        self.model_output_text.config(state=tk.NORMAL)
        self.model_output_text.delete("1.0", tk.END)
        self.model_output_text.insert(tk.END, f"Model: {model_name}\n")
        self.model_output_text.insert(tk.END, f"Raw Response: {raw_response}\n")
        self.model_output_text.insert(tk.END, f"Parsed Move: {parsed_move}\n")
        self.model_output_text.insert(tk.END, f"Validity: {validity}\n")
        self.model_output_text.insert(tk.END, f"Retry Count: {retry_count}\n")
        self.model_output_text.config(state=tk.DISABLED)
        
    def clear_model_output(self):
        self.model_output_text.config(state=tk.NORMAL)
        self.model_output_text.delete("1.0", tk.END)
        self.model_output_text.config(state=tk.DISABLED)

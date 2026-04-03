import tkinter as tk
from tkinter import scrolledtext

class MoveLogView(scrolledtext.ScrolledText):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.config(state=tk.DISABLED)

    def add_move(self, move_san, move_number, color):
        self.config(state=tk.NORMAL)
        if color == "white":
            self.insert(tk.END, f"{move_number}. {move_san} ")
        else:
            self.insert(tk.END, f"{move_san}\n")
        self.config(state=tk.DISABLED)
        self.see(tk.END)
    
    def clear_log(self):
        self.config(state=tk.NORMAL)
        self.delete("1.0", tk.END)
        self.config(state=tk.DISABLED)

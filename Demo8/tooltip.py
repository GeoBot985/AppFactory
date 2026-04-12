from __future__ import annotations

import tkinter as tk


class Tooltip:
    def __init__(self, widget: tk.Widget) -> None:
        self.widget = widget
        self.window: tk.Toplevel | None = None
        self.label: tk.Label | None = None

    def show(self, x: int, y: int, text: str) -> None:
        if self.window is None:
            self.window = tk.Toplevel(self.widget)
            self.window.withdraw()
            self.window.overrideredirect(True)
            self.window.attributes("-topmost", True)
            self.label = tk.Label(
                self.window,
                bg="#fff9db",
                fg="#1f1f1f",
                bd=1,
                relief="solid",
                padx=6,
                pady=4,
                justify="left",
                font=("Segoe UI", 9),
            )
            self.label.pack()
        assert self.label is not None
        self.label.configure(text=text)
        self.window.geometry(f"+{x + 14}+{y + 14}")
        self.window.deiconify()

    def hide(self) -> None:
        if self.window is not None:
            self.window.withdraw()

from __future__ import annotations

import tkinter as tk

from ui_main import TreemapApp


def main() -> None:
    root = tk.Tk()
    TreemapApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

from __future__ import annotations

import sys

from notes.cli import run_cli
from notes.ui import NotesApp


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if argv and argv[0].lower() == "ui":
        NotesApp().run()
        return 0
    run_cli()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

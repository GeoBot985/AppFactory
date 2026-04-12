from __future__ import annotations

import os
import subprocess


def open_in_explorer(path: str, select_file: bool | None = None) -> None:
    normalized = os.path.normpath(path)
    if not os.path.exists(normalized):
        raise FileNotFoundError("Path no longer exists.")

    if select_file is None:
        select_file = os.path.isfile(normalized)

    if select_file:
        subprocess.Popen(["explorer", f"/select,{normalized}"])
    else:
        subprocess.Popen(["explorer", normalized])

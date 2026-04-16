from __future__ import annotations

import difflib


def build_change_summary(path: str, before: str, after: str, max_lines: int = 40) -> str:
    diff_lines = list(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"{path}:before",
            tofile=f"{path}:after",
            lineterm="",
        )
    )
    if len(diff_lines) > max_lines:
        diff_lines = diff_lines[:max_lines] + ["... [diff truncated]"]
    return "\n".join(diff_lines)

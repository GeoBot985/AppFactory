from __future__ import annotations

import difflib
from pathlib import Path


def generate_unified_diff(old_content: str, new_content: str, file_path: str) -> str:
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}"
    )
    return "".join(diff)


def save_diff(run_folder: Path, relative_path: str, diff_text: str) -> Path:
    diffs_dir = run_folder / "diffs"
    diffs_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize path for filename
    sanitized_name = relative_path.replace("/", "_").replace("\\", "_") + ".diff"
    target = diffs_dir / sanitized_name
    target.write_text(diff_text, encoding="utf-8")
    return target

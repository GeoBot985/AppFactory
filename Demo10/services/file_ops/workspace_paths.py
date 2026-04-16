from __future__ import annotations

from pathlib import Path


def validate_workspace_path(project_root: str | Path, raw_path: str) -> tuple[bool, str, str]:
    root = Path(project_root).expanduser().resolve()
    if not raw_path:
        return False, "", "invalid_operation_schema: empty path"

    candidate = Path(raw_path)
    if candidate.is_absolute():
        return False, "", "path_outside_workspace: absolute path not allowed"

    try:
        normalized = (root / candidate).resolve()
    except Exception as exc:
        return False, "", f"invalid_operation_schema: invalid path {raw_path}: {exc}"

    try:
        normalized.relative_to(root)
    except ValueError:
        return False, "", f"path_outside_workspace: {raw_path}"

    return True, str(normalized), ""

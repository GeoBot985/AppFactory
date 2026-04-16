from __future__ import annotations

from pathlib import Path


def build_simulated_workspace_overlay(project_root: str | Path, file_payloads: dict[str, str | None]) -> dict[str, str]:
    root = Path(project_root).expanduser().resolve()
    overlay: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel in file_payloads:
            payload = file_payloads[rel]
            if payload is None:
                continue
            overlay[rel] = payload
            continue
        try:
            overlay[rel] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    for rel, payload in sorted(file_payloads.items()):
        if rel not in overlay and payload is not None:
            overlay[rel] = payload
    return overlay

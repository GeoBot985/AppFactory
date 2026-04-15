from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any


class AuditLogService:
    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.runs_dir = self.workspace_root / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def create_run_folder(self, slot_id: int) -> Path:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        run_folder = self.runs_dir / f"{timestamp}_slot_{slot_id}"
        run_folder.mkdir(parents=True, exist_ok=True)
        (run_folder / "files_changed").mkdir(parents=True, exist_ok=True)
        return run_folder

    def log_artifact(self, run_folder: Path, filename: str, content: Any):
        target = run_folder / filename
        if isinstance(content, (dict, list)):
            with target.open("w", encoding="utf-8") as f:
                json.dump(content, f, indent=2)
        else:
            target.write_text(str(content), encoding="utf-8")

    def capture_file_change(self, run_folder: Path, project_root: Path, relative_path: str):
        source = project_root / relative_path
        if source.exists() and source.is_file():
            # Create subdirectories in files_changed if needed
            target = run_folder / "files_changed" / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

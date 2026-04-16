from __future__ import annotations
import hashlib
from pathlib import Path
from typing import List, Optional
from .impact_model import FileDiff
from editing.diffing import generate_unified_diff

class DiffBuilder:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.max_diff_lines = 100

    def build_file_diff(self, path: str, op_type: str, new_content: Optional[str] = None) -> FileDiff:
        full_path = self.project_root / path
        before_content = ""
        if full_path.exists() and full_path.is_file():
            before_content = full_path.read_text(encoding="utf-8")

        before_hash = self._hash_content(before_content) if before_content else None
        after_hash = self._hash_content(new_content) if new_content is not None else None

        line_count_before = len(before_content.splitlines()) if before_content else 0
        line_count_after = len(new_content.splitlines()) if new_content is not None else 0

        diff_text = ""
        if op_type == "delete_file":
            diff_text = f"--- {path}\n+++ /dev/null\n@@ -1,{line_count_before} +0,0 @@\n"
            diff_text += "\n".join([f"-{line}" for line in before_content.splitlines()[:self.max_diff_lines]])
        elif op_type in ["create_file", "replace_file", "modify"]:
            diff_text = generate_unified_diff(before_content, new_content or "", path)
            # Bounded lines
            lines = diff_text.splitlines()
            if len(lines) > self.max_diff_lines:
                diff_text = "\n".join(lines[:self.max_diff_lines]) + "\n... (diff truncated)"

        return FileDiff(
            path=path,
            change_type=op_type,
            before_hash=before_hash,
            after_hash=after_hash,
            line_count_before=line_count_before,
            line_count_after=line_count_after,
            diff_preview=diff_text,
            is_large_change=abs(line_count_after - line_count_before) > 200 or len(diff_text.splitlines()) > 500
        )

    def _hash_content(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

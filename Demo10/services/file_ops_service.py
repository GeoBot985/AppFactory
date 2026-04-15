from __future__ import annotations

from pathlib import Path


class FileOpsService:
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).expanduser().resolve()

    def _safe_path(self, relative_path: str) -> Path:
        # Prevent parent traversal and absolute paths
        if ".." in relative_path or relative_path.startswith("/") or relative_path.startswith("\\"):
            raise ValueError(f"Path traversal or absolute path detected: {relative_path}")

        try:
            target_path = (self.project_root / relative_path).resolve()
        except Exception as exc:
            raise ValueError(f"Invalid path {relative_path}: {exc}")

        if not str(target_path).startswith(str(self.project_root)):
            raise ValueError(f"Path traversal detected: {relative_path}")

        return target_path

    def create(self, relative_path: str, content: str) -> str:
        target = self._safe_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"File created: {relative_path}"

    def modify(self, relative_path: str, content: str, mode: str = "replace") -> str:
        """
        In Phase 1, 'mode' can be 'replace' (overwrite full content) or 'append'.
        Future phases might support more complex patching.
        """
        target = self._safe_path(relative_path)
        if not target.exists():
            raise FileNotFoundError(f"File not found: {relative_path}")

        if mode == "append":
            with target.open("a", encoding="utf-8") as f:
                f.write(content)
            return f"Content appended to: {relative_path}"
        else:
            # Default is replace
            target.write_text(content, encoding="utf-8")
            return f"File modified: {relative_path}"

    def delete(self, relative_path: str) -> str:
        target = self._safe_path(relative_path)
        if target.exists():
            if target.is_file():
                target.unlink()
                return f"File deleted: {relative_path}"
            else:
                raise ValueError(f"Target is not a file: {relative_path}")
        return f"File already does not exist: {relative_path}"

from __future__ import annotations

from pathlib import Path

from services.file_ops.executor import FileOperationExecutor
from services.file_ops.models import FileOperation


class FileOpsService:
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).expanduser().resolve()
        self.executor = FileOperationExecutor()

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
        result = self.execute_plan(
            [
                FileOperation(
                    op_id="create_1",
                    op_type="create_file",
                    path=relative_path,
                    content=content,
                    source_stage="file_ops_service.create",
                )
            ],
            mode="apply",
        )
        if result.failed_count:
            raise ValueError(result.results[0].failure_reason or "create failed")
        return f"File created: {relative_path}"

    def modify(self, relative_path: str, content: str, mode: str = "replace") -> str:
        """
        In Phase 1, 'mode' can be 'replace' (overwrite full content) or 'append'.
        Future phases might support more complex patching.
        """
        if mode == "append":
            target = self._safe_path(relative_path)
            if not target.exists():
                raise FileNotFoundError(f"File not found: {relative_path}")
            existing = target.read_text(encoding="utf-8", errors="replace")
            content = existing + content

        result = self.execute_plan(
            [
                FileOperation(
                    op_id="replace_1",
                    op_type="replace_file",
                    path=relative_path,
                    content=content,
                    source_stage="file_ops_service.modify",
                )
            ],
            mode="apply",
        )
        if result.failed_count:
            reason = result.results[0].failure_reason or "modify failed"
            if "file_not_found" in reason:
                raise FileNotFoundError(f"File not found: {relative_path}")
            raise ValueError(reason)
        return f"File modified: {relative_path}"

    def delete(self, relative_path: str) -> str:
        result = self.execute_plan(
            [
                FileOperation(
                    op_id="delete_1",
                    op_type="delete_file",
                    path=relative_path,
                    source_stage="file_ops_service.delete",
                )
            ],
            mode="apply",
        )
        if result.failed_count:
            reason = result.results[0].failure_reason or "delete failed"
            if "file_not_found" in reason:
                return f"File already does not exist: {relative_path}"
            raise ValueError(reason)
        return f"File deleted: {relative_path}"

    def execute_plan(self, operations: list[FileOperation], mode: str = "apply"):
        return self.executor.execute(self.project_root, operations, mode=mode)  # type: ignore[arg-type]

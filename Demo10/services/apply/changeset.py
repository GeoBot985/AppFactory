from __future__ import annotations
import hashlib
import uuid
from typing import List, Any, Optional, Union
from pathlib import Path
from .models import ChangeSet, ChangeEntry, OperationType
from services.file_ops.models import FileOperation, FileMutationResult

class ChangeSetBuilder:
    def __init__(self, project_root: Path):
        self.project_root = project_root

    def build_changeset(self, run_id: str, operations: List[Union[FileOperation, FileMutationResult]]) -> ChangeSet:
        entries = []
        for op in operations:
            entry = self._normalize_operation(op)
            entries.append(entry)

        return ChangeSet(
            changeset_id=f"cs_{uuid.uuid4().hex[:8]}",
            run_id=run_id,
            entries=entries
        )

    def _normalize_operation(self, op: Union[FileOperation, FileMutationResult]) -> ChangeEntry:
        path = op.path

        # Determine operation type
        op_type_str = op.op_type
        op_map = {
            "create_file": OperationType.CREATE,
            "replace_file": OperationType.MODIFY,
            "patch_file": OperationType.MODIFY,
            "delete_file": OperationType.DELETE
        }
        op_type = op_map.get(op_type_str, OperationType.MODIFY)

        before_hash = getattr(op, 'before_hash', None)
        after_hash = getattr(op, 'after_hash', None)
        content = getattr(op, 'content', None)

        # In FileOperation, content is often provided but after_hash is not pre-calculated
        if content is not None and after_hash is None:
            after_hash = self._hash_string(content)
        patch = getattr(op, 'patch_blocks', None)
        source_task_id = getattr(op, 'op_id', 'unknown')

        # If it's a FileMutationResult, we might have more info
        if isinstance(op, FileMutationResult):
            # after_hash should be present if successful dry-run
            pass

        # If before_hash is missing, try to get it from disk
        if before_hash is None:
            full_path = self.project_root / path
            if full_path.exists() and full_path.is_file():
                before_hash = self._hash_file(full_path)

        return ChangeEntry(
            path=path,
            operation_type=op_type,
            before_hash=before_hash,
            after_hash=after_hash,
            content=content,
            patch=patch,
            source_task_id=source_task_id
        )

    def _hash_file(self, path: Path) -> str:
        try:
            return self._hash_string(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return ""

    def _hash_string(self, content: str) -> str:
        if content is None: return ""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

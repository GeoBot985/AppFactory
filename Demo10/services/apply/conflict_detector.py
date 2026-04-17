from __future__ import annotations
import hashlib
from pathlib import Path
from typing import List, Optional
from .models import ChangeSet, ChangeEntry, ConflictReport, ConflictEntry, ConflictType, OperationType

class ConflictDetector:
    def __init__(self, project_root: Path):
        self.project_root = project_root

    def detect_conflicts(self, changeset: ChangeSet) -> ConflictReport:
        report = ConflictReport(run_id=changeset.run_id)

        for entry in changeset.entries:
            conflict = self._check_entry(entry)
            if conflict:
                report.conflicts.append(conflict)

        report.is_blocking = any(c.severity == "error" for c in report.conflicts)
        return report

    def _check_entry(self, entry: ChangeEntry) -> Optional[ConflictEntry]:
        full_path = self.project_root / entry.path
        exists = full_path.exists()

        current_hash = None
        if exists and full_path.is_file():
            current_hash = self._hash_file(full_path)

        # 1. CREATE rules
        if entry.operation_type == OperationType.CREATE:
            if exists:
                # If already exists with same content, it's not really a conflict (idempotency)
                # But if content differs, it's a conflict.
                if entry.after_hash and current_hash != entry.after_hash:
                    return ConflictEntry(
                        path=entry.path,
                        conflict_type=ConflictType.FILE_ALREADY_EXISTS,
                        expected_state="non-existent",
                        actual_state=f"exists (hash={current_hash[:8]})",
                        task_id=entry.source_task_id
                    )
            return None

        # 2. MODIFY rules
        if entry.operation_type == OperationType.MODIFY:
            if not exists:
                return ConflictEntry(
                    path=entry.path,
                    conflict_type=ConflictType.FILE_MISSING,
                    expected_state="exists",
                    actual_state="missing",
                    task_id=entry.source_task_id
                )

            # Idempotency check: if current hash matches after_hash, no conflict (already applied)
            if current_hash == entry.after_hash:
                return None

            # Baseline check: current hash must match before_hash
            if entry.before_hash and current_hash != entry.before_hash:
                return ConflictEntry(
                    path=entry.path,
                    conflict_type=ConflictType.HASH_MISMATCH,
                    expected_state=f"hash={entry.before_hash[:8]}",
                    actual_state=f"hash={current_hash[:8]}",
                    task_id=entry.source_task_id
                )
            return None

        # 3. DELETE rules
        if entry.operation_type == OperationType.DELETE:
            if not exists:
                return None # Idempotent delete

            if entry.before_hash and current_hash != entry.before_hash:
                return ConflictEntry(
                    path=entry.path,
                    conflict_type=ConflictType.UNEXPECTED_MODIFICATION,
                    expected_state=f"hash={entry.before_hash[:8]}",
                    actual_state=f"hash={current_hash[:8]}",
                    task_id=entry.source_task_id
                )
            return None

        return None

    def _hash_file(self, path: Path) -> str:
        try:
            return hashlib.sha256(path.read_text(encoding="utf-8", errors="replace").encode("utf-8")).hexdigest()
        except Exception:
            return ""

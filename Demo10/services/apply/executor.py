from __future__ import annotations
import uuid
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from .models import (
    ChangeSet, ChangeEntry, ApplyTransaction, TransactionStatus,
    OperationType, ConflictReport
)
from .conflict_detector import ConflictDetector
from .verifier import Verifier
from services.file_ops.patcher import apply_patch_blocks

class DeterministicExecutor:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.detector = ConflictDetector(project_root)
        self.verifier = Verifier(project_root)

    def execute(self, changeset: ChangeSet, force: bool = False) -> ApplyTransaction:
        transaction = ApplyTransaction(
            transaction_id=f"tx_{uuid.uuid4().hex[:8]}",
            run_id=changeset.run_id,
            changeset_id=changeset.changeset_id
        )

        # 1. Pre-apply conflict detection
        conflict_report = self.detector.detect_conflicts(changeset)
        transaction.conflict_report = conflict_report

        if conflict_report.is_blocking and not force:
            transaction.status = TransactionStatus.FAILED
            transaction.end_time = time.strftime("%Y-%m-%dT%H:%M:%S")
            return transaction

        # 2. Apply mutations idempotently
        try:
            for entry in changeset.entries:
                applied = self._apply_entry(entry)
                if applied:
                    transaction.applied_files.append(entry.path)
                else:
                    transaction.skipped_files.append(entry.path)

            transaction.status = TransactionStatus.APPLIED
        except Exception as e:
            transaction.status = TransactionStatus.PARTIALLY_APPLIED
            transaction.metrics["error"] = str(e)

        # 3. Post-apply verification
        verification_report = self.verifier.verify(changeset)
        if not verification_report.success:
            transaction.verification_errors = verification_report.errors
            if transaction.status == TransactionStatus.APPLIED:
                transaction.status = TransactionStatus.FAILED

        transaction.end_time = time.strftime("%Y-%m-%dT%H:%M:%S")
        return transaction

    def _apply_entry(self, entry: ChangeEntry) -> bool:
        full_path = self.project_root / entry.path

        # Current state
        exists = full_path.exists()
        current_hash = None
        if exists and full_path.is_file():
            current_hash = self._hash_file(full_path)

        # Idempotency check
        if entry.operation_type == OperationType.DELETE:
            if not exists:
                return False
        elif entry.after_hash is not None and current_hash == entry.after_hash:
            return False # Already applied

        if entry.operation_type == OperationType.CREATE:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(entry.content or "", encoding="utf-8", newline="")
            return True

        elif entry.operation_type == OperationType.MODIFY:
            if entry.content is not None:
                full_path.write_text(entry.content, encoding="utf-8", newline="")
                return True
            elif entry.patch is not None:
                before_text = full_path.read_text(encoding="utf-8")
                outcome = apply_patch_blocks(before_text, entry.patch)
                full_path.write_text(outcome.content, encoding="utf-8", newline="")
                return True
            return False

        elif entry.operation_type == OperationType.DELETE:
            if exists:
                full_path.unlink()
                return True
            return False

        return False

    def _hash_file(self, path: Path) -> str:
        try:
            return self.verifier._hash_file(path)
        except Exception:
            return ""

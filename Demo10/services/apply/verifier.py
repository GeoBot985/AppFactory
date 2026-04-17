from __future__ import annotations
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
from .models import ChangeSet, OperationType

@dataclass
class VerificationReport:
    success: bool
    errors: List[str] = field(default_factory=list)

class Verifier:
    def __init__(self, project_root: Path):
        self.project_root = project_root

    def verify(self, changeset: ChangeSet) -> VerificationReport:
        errors = []
        for entry in changeset.entries:
            full_path = self.project_root / entry.path

            if entry.operation_type == OperationType.DELETE:
                if full_path.exists():
                    errors.append(f"Verification failed: {entry.path} should have been deleted but still exists.")
            else:
                if not full_path.exists():
                    errors.append(f"Verification failed: {entry.path} should exist but is missing.")
                    continue

                current_hash = self._hash_file(full_path)
                if entry.after_hash and current_hash != entry.after_hash:
                    errors.append(f"Verification failed: {entry.path} hash mismatch. Expected {entry.after_hash[:8]}, got {current_hash[:8]}.")

        return VerificationReport(success=len(errors) == 0, errors=errors)

    def _hash_file(self, path: Path) -> str:
        try:
            return hashlib.sha256(path.read_text(encoding="utf-8", errors="replace").encode("utf-8")).hexdigest()
        except Exception:
            return ""

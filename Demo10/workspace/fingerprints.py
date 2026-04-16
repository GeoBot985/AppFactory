import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from .models import WorkspaceFingerprint

class FingerprintService:
    def __init__(self, hash_algorithm: str = "sha256"):
        self.hash_algorithm = hash_algorithm

    def compute_fingerprint(self, workspace_path: Path, ignore_patterns: Optional[List[str]] = None) -> WorkspaceFingerprint:
        if ignore_patterns is None:
            ignore_patterns = [".git", "__pycache__", "runs", "regression_runs"]

        entries: Dict[str, str] = {}
        all_paths = sorted(workspace_path.rglob("*"))

        for path in all_paths:
            if not path.is_file():
                continue

            # Check if any parent directory is in ignore_patterns or the file itself
            relative_path = path.relative_to(workspace_path)
            if any(part in ignore_patterns for part in relative_path.parts):
                continue

            entries[str(relative_path)] = self._compute_file_hash(path)

        summary_hash = self._compute_summary_hash(entries)

        return WorkspaceFingerprint(
            file_count=len(entries),
            summary_hash=summary_hash,
            entries=entries
        )

    def _compute_file_hash(self, file_path: Path) -> str:
        # For small files, we can just read the whole thing.
        # For SPEC 014, we capture size/mtime as well as content hash for deterministic identity.
        # But per spec requirement: "relative path, size, modified time. Then compute normalized summary hash"
        # "Optional stronger mode: content hash per file for .py, .json, .yaml, .yml, .md, etc."

        hasher = hashlib.new(self.hash_algorithm)
        stat = file_path.stat()

        # Include metadata in the hash to be sensitive to mtime/size changes
        hasher.update(str(stat.st_size).encode())
        hasher.update(str(int(stat.st_mtime)).encode())

        # Always content hash for correctness as recommended in SPEC 014
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
        except PermissionError:
            # If we can't read it, just use metadata
            pass

        return hasher.hexdigest()

    def _compute_summary_hash(self, entries: Dict[str, str]) -> str:
        hasher = hashlib.new(self.hash_algorithm)
        # Sort keys for determinism
        for path in sorted(entries.keys()):
            hasher.update(path.encode())
            hasher.update(entries[path].encode())
        return hasher.hexdigest()

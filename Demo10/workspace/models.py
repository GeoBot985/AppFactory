from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

class WorkspaceRole(Enum):
    CANONICAL = "canonical"
    SNAPSHOT_SOURCE = "snapshot_source"
    EXECUTION = "execution"
    PROMOTION_TARGET = "promotion_target"

class ExecutionMode(Enum):
    PROMOTE_ON_SUCCESS = "promote_on_success"
    DRY_RUN = "dry_run"
    VERIFY_ONLY = "verify_only"
    REGRESSION_CASE = "regression_case"

class SourcePolicy(Enum):
    PROMOTED_HEAD = "promoted_head"
    FIXED_BASE = "fixed_base"

class PromotionStatus(Enum):
    APPLIED = "applied"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    FAILED = "failed"

@dataclass
class WorkspaceFingerprint:
    file_count: int
    summary_hash: str
    entries: Dict[str, str]  # relative_path -> hash
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "file_count": self.file_count,
            "summary_hash": self.summary_hash,
            "entries": self.entries,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "WorkspaceFingerprint":
        return cls(
            file_count=int(data.get("file_count", 0)),
            summary_hash=str(data.get("summary_hash", "")),
            entries=dict(data.get("entries", {})),
            created_at=str(data.get("created_at", datetime.now().isoformat())),
        )

@dataclass
class SnapshotManifest:
    run_id: str
    spec_id: str
    source_workspace: str
    execution_workspace: str
    mode: str
    source_fingerprint: WorkspaceFingerprint
    manifest_path: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "spec_id": self.spec_id,
            "source_workspace": self.source_workspace,
            "execution_workspace": self.execution_workspace,
            "mode": self.mode,
            "created_at": self.created_at,
            "manifest_path": self.manifest_path,
            "source_fingerprint": self.source_fingerprint.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "SnapshotManifest":
        manifest_path = str(data.get("manifest_path", ""))
        if not manifest_path:
            manifest_path = str(Path(data.get("execution_workspace", "")).parent / "snapshot_manifest.json")
        return cls(
            run_id=str(data.get("run_id", "")),
            spec_id=str(data.get("spec_id", "")),
            source_workspace=str(data.get("source_workspace", "")),
            execution_workspace=str(data.get("execution_workspace", "")),
            mode=str(data.get("mode", "")),
            source_fingerprint=WorkspaceFingerprint.from_dict(dict(data.get("source_fingerprint", {}))),
            manifest_path=manifest_path,
            created_at=str(data.get("created_at", datetime.now().isoformat())),
        )

@dataclass
class PromotionReport:
    promotion_status: PromotionStatus
    reason: str
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    files_deleted: List[str] = field(default_factory=list)
    target_workspace: str = ""
    applied_at: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class ConflictEntry:
    path: str
    source_snapshot_hash: str
    current_canonical_hash: str

@dataclass
class ConflictReport:
    promotion_status: PromotionStatus = PromotionStatus.BLOCKED
    reason: str = "PROMOTION_CONFLICT"
    conflicts: List[ConflictEntry] = field(default_factory=list)

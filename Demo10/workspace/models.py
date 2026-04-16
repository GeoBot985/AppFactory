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

@dataclass
class SnapshotFileEntry:
    relative_path: str
    exists: bool
    size: int
    content_hash: str
    is_binary: bool
    storage_ref: str = ""

    def to_dict(self) -> dict:
        return {
            "relative_path": self.relative_path,
            "exists": self.exists,
            "size": self.size,
            "content_hash": self.content_hash,
            "is_binary": self.is_binary,
            "storage_ref": self.storage_ref
        }

@dataclass
class WorkspaceSnapshot:
    snapshot_id: str
    workspace_root: str
    created_at: str
    source_run_id: str
    source_compiled_plan_id: str
    file_count: int
    excluded_count: int
    storage_mode: str
    status: str
    manifest: List[SnapshotFileEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "workspace_root": self.workspace_root,
            "created_at": self.created_at,
            "source_run_id": self.source_run_id,
            "source_compiled_plan_id": self.source_compiled_plan_id,
            "file_count": self.file_count,
            "excluded_count": self.excluded_count,
            "storage_mode": self.storage_mode,
            "status": self.status,
            "manifest": [e.to_dict() for e in self.manifest]
        }

@dataclass
class RestoreRequest:
    request_id: str
    snapshot_id: str
    target_workspace: str
    requested_by: str
    reason: str
    force: bool = False

@dataclass
class RestoreRun:
    restore_run_id: str
    snapshot_id: str
    workspace_root: str
    requested_by: str
    reason: str
    base_run_id: str
    started_at: str
    completed_at: str = ""
    status: str = "pending"
    files_restored_count: int = 0
    files_removed_count: int = 0
    verification_status: str = "pending"
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "restore_run_id": self.restore_run_id,
            "snapshot_id": self.snapshot_id,
            "workspace_root": self.workspace_root,
            "requested_by": self.requested_by,
            "reason": self.reason,
            "base_run_id": self.base_run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "files_restored_count": self.files_restored_count,
            "files_removed_count": self.files_removed_count,
            "verification_status": self.verification_status,
            "warnings": self.warnings,
            "errors": self.errors
        }

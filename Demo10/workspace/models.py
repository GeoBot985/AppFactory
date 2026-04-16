from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime

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

@dataclass
class SnapshotManifest:
    run_id: str
    spec_id: str
    source_workspace: str
    execution_workspace: str
    mode: str
    source_fingerprint: WorkspaceFingerprint
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

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

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime

class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

@dataclass
class FileDiff:
    path: str
    change_type: str  # create, modify, delete
    before_hash: Optional[str] = None
    after_hash: Optional[str] = None
    line_count_before: int = 0
    line_count_after: int = 0
    diff_preview: str = ""
    is_large_change: bool = False

@dataclass
class ImpactSummary:
    total_files: int = 0
    files_created: int = 0
    files_modified: int = 0
    files_deleted: int = 0
    estimated_loc_change: int = 0
    modules_affected: int = 0
    tests_affected: int = 0
    has_critical_changes: bool = False

@dataclass
class ImpactPreview:
    preview_id: str
    compiled_plan_id: str
    workspace_hash: str
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    risk_level: RiskLevel = RiskLevel.LOW
    risk_reasons: List[str] = field(default_factory=list)
    summary: ImpactSummary = field(default_factory=ImpactSummary)
    file_diffs: List[FileDiff] = field(default_factory=list)

@dataclass
class ApprovalState:
    approval_required: bool = False
    status: ApprovalStatus = ApprovalStatus.PENDING
    timestamp: Optional[str] = None
    source: str = "system"  # user, system
    reason: Optional[str] = None

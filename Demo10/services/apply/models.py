from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Any
from datetime import datetime

class OperationType(Enum):
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"

class TransactionStatus(Enum):
    PENDING = "pending"
    APPLIED = "applied"
    PARTIALLY_APPLIED = "partially_applied"
    FAILED = "failed"

class ConflictType(Enum):
    HASH_MISMATCH = "hash_mismatch"
    FILE_ALREADY_EXISTS = "file_already_exists"
    FILE_MISSING = "file_missing"
    UNEXPECTED_MODIFICATION = "unexpected_modification"
    OVERLAPPING_PATCH_CONFLICT = "overlapping_patch_conflict"
    PROTECTED_PATH_VIOLATION = "protected_path_violation"

@dataclass(frozen=True)
class ChangeEntry:
    path: str
    operation_type: OperationType
    before_hash: Optional[str] = None # Expected hash before apply
    after_hash: Optional[str] = None  # Expected hash after apply
    content: Optional[str] = None      # Full content if CREATE/REPLACE
    patch: Optional[Any] = None       # Patch blocks or unified diff if MODIFY
    source_task_id: str = "unknown"

@dataclass
class ChangeSet:
    changeset_id: str
    run_id: str
    entries: List[ChangeEntry] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ConflictEntry:
    path: str
    conflict_type: ConflictType
    expected_state: str
    actual_state: str
    task_id: str
    severity: str = "error" # error, warning

@dataclass
class ConflictReport:
    run_id: str
    conflicts: List[ConflictEntry] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    is_blocking: bool = True

@dataclass
class ApplyTransaction:
    transaction_id: str
    run_id: str
    changeset_id: str
    status: TransactionStatus = TransactionStatus.PENDING
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None
    conflict_report: Optional[ConflictReport] = None
    applied_files: List[str] = field(default_factory=list)
    skipped_files: List[str] = field(default_factory=list)
    verification_errors: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


class OperationType(Enum):
    INSERT_BEFORE = "insert_before"
    INSERT_AFTER = "insert_after"
    REPLACE_BLOCK = "replace_block"
    APPEND_IF_MISSING = "append_if_missing"
    ENSURE_IMPORT = "ensure_import"
    ENSURE_FUNCTION = "ensure_function"
    ENSURE_CLASS = "ensure_class"
    DELETE_BLOCK = "delete_block"


class AnchorType(Enum):
    FUNCTION = "function"
    CLASS = "class"
    IMPORT = "import"
    LINE_MATCH = "line_match"
    REGION_MARKER = "region_marker"
    FILE_START = "file_start"
    FILE_END = "file_end"


class MatchMode(Enum):
    EXACT = "exact"
    CONTAINS = "contains"
    REGEX = "regex"
    SIGNATURE_LIKE = "signature_like"


@dataclass
class EditConstraints:
    must_be_unique: bool = True
    create_if_missing: bool = False
    fail_if_missing: bool = True
    fail_if_multiple: bool = True
    ensure_mode: str = "replace_if_exists"  # create_only | replace_if_exists | fail_if_exists


@dataclass
class EditInstruction:
    task_id: str
    file_path: str
    operation: OperationType
    anchor_type: AnchorType
    anchor_value: str
    payload: str
    match_mode: MatchMode = MatchMode.EXACT
    constraints: EditConstraints = field(default_factory=EditConstraints)


class AnchorStatus(Enum):
    OK = "ok"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


@dataclass
class AnchorMatch:
    start_line: int  # 0-indexed
    end_line: int    # 0-indexed, inclusive
    start_char: int
    end_char: int
    preview: str


@dataclass
class AnchorResolution:
    status: AnchorStatus
    matches: list[AnchorMatch] = field(default_factory=list)
    selected_match: Optional[AnchorMatch] = None


class EditStatus(Enum):
    APPLIED = "applied"
    NO_OP = "no_op"
    FAILED = "failed"


@dataclass
class IdempotencyRecord:
    status: str  # inserted | replaced | skipped_existing | failed_conflict
    reason: str


@dataclass
class ValidationReport:
    syntax_ok: bool
    symbol_check_ok: bool
    error_message: Optional[str] = None


@dataclass
class ChangeSummary:
    lines_before: int
    lines_after: int
    delta: int


@dataclass
class EditResult:
    task_id: str
    file_path: str
    status: EditStatus
    operation: OperationType
    anchor_resolution: AnchorResolution
    backup_path: Optional[str] = None
    validation: Optional[ValidationReport] = None
    idempotency_check: Optional[IdempotencyRecord] = None
    change_summary: Optional[ChangeSummary] = None
    reason: str = ""
    preview_before: str = ""
    preview_after: str = ""
    diff_path: Optional[str] = None

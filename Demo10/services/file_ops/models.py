from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


OperationType = Literal["create_file", "replace_file", "patch_file", "delete_file"]
PatchMatchType = Literal["exact", "regex"]
ExecutionMode = Literal["dry-run", "apply"]


@dataclass(frozen=True)
class PatchBlock:
    match_type: PatchMatchType
    target: str
    replacement: str
    expected_matches: int = 1
    replace_all: bool = False
    context_label: str = ""
    required: bool = True


@dataclass(frozen=True)
class FileOperation:
    op_id: str
    op_type: OperationType
    path: str
    content: str = ""
    patch_blocks: list[PatchBlock] = field(default_factory=list)
    reason: str = ""
    source_stage: str = ""
    allow_overwrite: bool = False


@dataclass(frozen=True)
class ValidatedOperation:
    operation: FileOperation
    raw_path: str
    normalized_path: str


@dataclass
class PatchOutcome:
    content: str
    matches_found: int
    matches_replaced: int
    content_changed: bool


@dataclass
class FileMutationResult:
    op_id: str
    op_type: OperationType
    path: str
    normalized_path: str
    status: str
    matches_found: int = 0
    matches_replaced: int = 0
    content_changed: bool = False
    before_hash: str = ""
    after_hash: str = ""
    before_size: int = 0
    after_size: int = 0
    line_delta: int = 0
    size_delta: int = 0
    failure_reason: str = ""
    failure_code: str = ""
    diff_preview: str = ""


@dataclass
class MutationLedgerEntry:
    order_index: int
    timestamp: str
    op_id: str
    op_type: OperationType
    target_path: str
    normalized_path: str
    validated: bool
    executed: bool
    success: bool
    failure_reason: str = ""
    failure_code: str = ""
    before_hash: str = ""
    after_hash: str = ""
    before_size: int = 0
    after_size: int = 0


@dataclass
class FileOperationBatchResult:
    project_root: str
    mode: ExecutionMode
    status: str
    results: list[FileMutationResult] = field(default_factory=list)
    ledger: list[MutationLedgerEntry] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    created_count: int = 0
    modified_count: int = 0
    deleted_count: int = 0
    unchanged_count: int = 0
    failed_count: int = 0

    def to_summary(self) -> str:
        return (
            f"mode={self.mode}, created={self.created_count}, modified={self.modified_count}, "
            f"deleted={self.deleted_count}, unchanged={self.unchanged_count}, failed={self.failed_count}"
        )

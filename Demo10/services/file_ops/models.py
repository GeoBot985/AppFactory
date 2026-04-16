from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from services.batch.models import BatchValidationSummary
from services.testing.runner import TestRunResult


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
class CodeValidationResult:
    path: str
    language: str
    status: str
    error_type: str = ""
    line_number: int = 0
    column_offset: int = 0
    error_message: str = ""
    offending_line: str = ""
    check_name: str = ""


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
    validation: CodeValidationResult | None = None


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
    validation_status: str = ""
    validation_error: str = ""


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
    files_validated: int = 0
    files_passed: int = 0
    files_failed: int = 0
    batch_summary: BatchValidationSummary | None = None
    test_summary: TestRunResult | None = None

    def to_summary(self) -> str:
        batch_status = self.batch_summary.batch_validation_status if self.batch_summary else "batch_unknown"
        test_status = self.test_summary.status if self.test_summary else "tests_skipped"
        return (
            f"mode={self.mode}, created={self.created_count}, modified={self.modified_count}, "
            f"deleted={self.deleted_count}, unchanged={self.unchanged_count}, failed={self.failed_count}, "
            f"validated={self.files_validated}, validation_failed={self.files_failed}, batch={batch_status}, tests={test_status}"
        )

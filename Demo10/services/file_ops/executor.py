from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from services.batch.coherence_validator import validate_batch_coherence
from services.code_validation import validate_file_content
from services.file_ops.diff_preview import build_change_summary
from services.file_ops.models import ExecutionMode, FileMutationResult, FileOperation, FileOperationBatchResult, MutationLedgerEntry
from services.file_ops.patcher import apply_patch_blocks
from services.file_ops.validator import validate_operation_plan


class OperationError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


class FileOperationExecutor:
    def execute(self, project_root: str | Path, operations: list[FileOperation], mode: ExecutionMode = "apply") -> FileOperationBatchResult:
        root = Path(project_root).expanduser().resolve()
        validated, validation_errors = validate_operation_plan(root, operations)
        batch = FileOperationBatchResult(
            project_root=str(root),
            mode=mode,
            status="failed" if validation_errors else "completed",
            validation_errors=validation_errors,
        )
        if validation_errors:
            return batch

        simulated_payloads: dict[str, str | None] = {}
        pending_writes: list[tuple[Path, FileOperation, str, FileMutationResult, MutationLedgerEntry]] = []
        for idx, item in enumerate(validated):
            result, ledger, after_text = self._execute_one(idx, Path(item.normalized_path), item.operation, "dry-run")
            batch.results.append(result)
            batch.ledger.append(ledger)
            if result.status != "failed":
                simulated_payloads[item.operation.path] = after_text
                pending_writes.append((Path(item.normalized_path), item.operation, after_text, result, ledger))
            if result.validation and result.validation.status != "skipped":
                batch.files_validated += 1
                if result.validation.status == "valid":
                    batch.files_passed += 1
                else:
                    batch.files_failed += 1
            if result.status == "created":
                batch.created_count += 1
            elif result.status == "modified":
                batch.modified_count += 1
            elif result.status == "deleted":
                batch.deleted_count += 1
            elif result.status == "unchanged":
                batch.unchanged_count += 1
            else:
                batch.failed_count += 1

        if batch.failed_count == 0:
            batch.batch_summary = validate_batch_coherence(root, [item.operation for item in validated], simulated_payloads)
            if batch.batch_summary.batch_validation_status.startswith("batch_invalid"):
                batch.status = "failed"
                batch.failed_count = max(batch.failed_count, 1)
                return batch
        else:
            batch.batch_summary = validate_batch_coherence(root, [item.operation for item in validated if item.operation.path in simulated_payloads], simulated_payloads)

        if mode == "apply":
            for target, op, after_text, result, ledger in pending_writes:
                if not self._apply_write(target, op, after_text):
                    failed_result = self._failed(
                        ledger.order_index,
                        ledger.timestamp,
                        op,
                        target,
                        "write_failed",
                        "write_failed",
                        before_hash=result.before_hash,
                        before_size=result.before_size,
                        validation=result.validation,
                        diff_preview=result.diff_preview,
                    )[0]
                    batch.results[ledger.order_index] = failed_result
                    batch.ledger[ledger.order_index].success = False
                    batch.ledger[ledger.order_index].failure_reason = "write_failed"
                    batch.ledger[ledger.order_index].failure_code = "write_failed"
                    batch.failed_count += 1
                    if result.status == "created":
                        batch.created_count -= 1
                    elif result.status == "modified":
                        batch.modified_count -= 1

        if batch.failed_count and (batch.created_count or batch.modified_count or batch.deleted_count or batch.unchanged_count):
            batch.status = "completed_with_failures"
        elif batch.failed_count:
            batch.status = "failed"
        else:
            batch.status = "completed"
        return batch

    def _execute_one(self, order_index: int, target: Path, op: FileOperation, mode: ExecutionMode):
        now = self._now()
        before_text = ""
        before_hash = ""
        before_size = 0
        if target.exists() and target.is_file():
            if self._is_binary(target) and op.op_type in {"replace_file", "patch_file"}:
                result, ledger = self._failed(order_index, now, op, target, "binary_file_not_supported", "binary_file_not_supported")
                return result, ledger, None
            before_text = target.read_text(encoding="utf-8", errors="replace")
            before_hash = self._hash(before_text)
            before_size = len(before_text)

        try:
            matches_found = 0
            matches_replaced = 0
            if op.op_type == "create_file":
                if target.exists() and not op.allow_overwrite:
                    raise OperationError("file_already_exists", "file_already_exists")
                after_text = op.content
                status = "created" if not target.exists() else "modified"
            elif op.op_type == "replace_file":
                if not target.exists() and not op.allow_overwrite:
                    raise OperationError("file_not_found", "file_not_found")
                after_text = op.content
                status = "modified" if target.exists() else "created"
            elif op.op_type == "patch_file":
                if not target.exists():
                    raise OperationError("file_not_found", "file_not_found")
                outcome = apply_patch_blocks(before_text, op.patch_blocks)
                after_text = outcome.content
                matches_found = outcome.matches_found
                matches_replaced = outcome.matches_replaced
                status = "unchanged" if not outcome.content_changed else "modified"
            elif op.op_type == "delete_file":
                if not target.exists():
                    raise OperationError("file_not_found", "file_not_found")
                after_text = ""
                status = "deleted"
            else:
                raise OperationError("invalid_operation_schema", "invalid_operation_schema")
        except OperationError as exc:
            result, ledger = self._failed(order_index, now, op, target, str(exc), exc.code, before_hash, before_size)
            return result, ledger, None
        except ValueError as exc:
            code = str(exc)
            result, ledger = self._failed(order_index, now, op, target, code, code, before_hash, before_size)
            return result, ledger, None

        after_hash = self._hash(after_text)
        after_size = len(after_text)
        line_delta = len(after_text.splitlines()) - len(before_text.splitlines())
        size_delta = after_size - before_size
        diff_preview = build_change_summary(op.path, before_text, "" if op.op_type == "delete_file" else after_text)
        validation = None

        if op.op_type != "delete_file":
            validation = validate_file_content(op.path, after_text)
            if validation.status == "invalid":
                result, ledger = self._failed(
                    order_index,
                    now,
                    op,
                    target,
                    validation.error_message or "code_validation_failed",
                    "code_validation_failed",
                    before_hash,
                    before_size,
                    validation=validation,
                    diff_preview=diff_preview,
                )
                return result, ledger, after_text

        if mode == "apply" and not self._apply_write(target, op, after_text):
            result, ledger = self._failed(order_index, now, op, target, "write_failed", "write_failed", before_hash, before_size)
            return result, ledger, after_text

        result = FileMutationResult(
            op_id=op.op_id,
            op_type=op.op_type,
            path=op.path,
            normalized_path=str(target),
            status=status,
            matches_found=matches_found,
            matches_replaced=matches_replaced,
            content_changed=before_text != after_text,
            before_hash=before_hash,
            after_hash=after_hash,
            before_size=before_size,
            after_size=after_size,
            line_delta=line_delta,
            size_delta=size_delta,
            diff_preview=diff_preview,
            validation=validation,
        )
        ledger = MutationLedgerEntry(
            order_index=order_index,
            timestamp=now,
            op_id=op.op_id,
            op_type=op.op_type,
            target_path=op.path,
            normalized_path=str(target),
            validated=True,
            executed=True,
            success=True,
            before_hash=before_hash,
            after_hash=after_hash,
            before_size=before_size,
            after_size=after_size,
            validation_status=validation.status if validation else "skipped",
            validation_error=validation.error_message if validation else "",
        )
        return result, ledger, after_text

    def _failed(self, order_index, timestamp, op, target, reason, code, before_hash="", before_size=0, validation=None, diff_preview=""):
        result = FileMutationResult(
            op_id=op.op_id,
            op_type=op.op_type,
            path=op.path,
            normalized_path=str(target),
            status="failed",
            failure_reason=reason,
            failure_code=code,
            before_hash=before_hash,
            before_size=before_size,
            diff_preview=diff_preview,
            validation=validation,
        )
        ledger = MutationLedgerEntry(
            order_index=order_index,
            timestamp=timestamp,
            op_id=op.op_id,
            op_type=op.op_type,
            target_path=op.path,
            normalized_path=str(target),
            validated=True,
            executed=True,
            success=False,
            failure_reason=reason,
            failure_code=code,
            before_hash=before_hash,
            before_size=before_size,
            validation_status=validation.status if validation else "",
            validation_error=validation.error_message if validation else "",
        )
        return result, ledger

    def _apply_write(self, target: Path, op: FileOperation, after_text: str) -> bool:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if op.op_type == "delete_file":
                if target.exists():
                    target.unlink()
            else:
                target.write_text(after_text, encoding="utf-8", newline="")
            return True
        except OSError:
            return False

    def _hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _is_binary(self, path: Path) -> bool:
        try:
            return b"\x00" in path.read_bytes()[:4096]
        except OSError:
            return False

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

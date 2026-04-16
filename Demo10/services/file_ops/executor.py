from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

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

        for idx, item in enumerate(validated):
            result, ledger = self._execute_one(idx, Path(item.normalized_path), item.operation, mode)
            batch.results.append(result)
            batch.ledger.append(ledger)
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
                return self._failed(order_index, now, op, target, "binary_file_not_supported", "binary_file_not_supported")
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
            return self._failed(order_index, now, op, target, str(exc), exc.code, before_hash, before_size)
        except ValueError as exc:
            code = str(exc)
            return self._failed(order_index, now, op, target, code, code, before_hash, before_size)

        after_hash = self._hash(after_text)
        after_size = len(after_text)
        line_delta = len(after_text.splitlines()) - len(before_text.splitlines())
        size_delta = after_size - before_size
        diff_preview = build_change_summary(op.path, before_text, "" if op.op_type == "delete_file" else after_text)

        if mode == "apply":
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                if op.op_type == "delete_file":
                    target.unlink()
                else:
                    target.write_text(after_text, encoding="utf-8", newline="")
            except OSError as exc:
                return self._failed(order_index, now, op, target, str(exc), "write_failed", before_hash, before_size)

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
        )
        return result, ledger

    def _failed(self, order_index, timestamp, op, target, reason, code, before_hash="", before_size=0):
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
        )
        return result, ledger

    def _hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _is_binary(self, path: Path) -> bool:
        try:
            return b"\x00" in path.read_bytes()[:4096]
        except OSError:
            return False

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

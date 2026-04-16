from __future__ import annotations

from pathlib import Path

from services.file_ops.models import FileOperation, ValidatedOperation
from services.file_ops.workspace_paths import validate_workspace_path


ALLOWED_OPS = {"create_file", "replace_file", "patch_file", "delete_file"}


def validate_operation_plan(project_root: str | Path, operations: list[FileOperation]) -> tuple[list[ValidatedOperation], list[str]]:
    validated: list[ValidatedOperation] = []
    errors: list[str] = []
    seen_paths: dict[str, str] = {}

    for op in operations:
        if op.op_type not in ALLOWED_OPS:
            errors.append(f"{op.op_id}: invalid_operation_schema: unsupported op_type {op.op_type}")
            continue
        if not op.op_id:
            errors.append("missing op_id")
            continue
        if op.path in seen_paths:
            errors.append(f"{op.op_id}: conflicting_operations: {op.path} already used by {seen_paths[op.path]}")
            continue
        seen_paths[op.path] = op.op_id

        if op.op_type in {"create_file", "replace_file"} and op.content == "":
            errors.append(f"{op.op_id}: invalid_operation_schema: content required for {op.op_type}")
            continue
        if op.op_type == "patch_file" and not op.patch_blocks:
            errors.append(f"{op.op_id}: invalid_operation_schema: patch_blocks required for patch_file")
            continue
        if op.op_type == "delete_file" and (op.content or op.patch_blocks):
            errors.append(f"{op.op_id}: invalid_operation_schema: delete_file cannot include content or patch_blocks")
            continue

        ok, normalized, reason = validate_workspace_path(project_root, op.path)
        if not ok:
            errors.append(f"{op.op_id}: {reason}")
            continue

        validated.append(ValidatedOperation(operation=op, raw_path=op.path, normalized_path=normalized))

    return validated, errors

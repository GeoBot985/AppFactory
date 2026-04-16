from __future__ import annotations

from services.file_ops.models import FileOperation
from services.targeting.models import ScopeContract


def validate_operation_plan_against_scope(operations: list[FileOperation], contract: ScopeContract) -> tuple[bool, list[str]]:
    errors: list[str] = []
    allowed = set(contract.editable_files)
    excluded = set(contract.excluded_files)
    for op in operations:
        if op.path in excluded:
            errors.append(f"{op.op_id}: scope_excluded_file: {op.path}")
            continue
        if allowed and op.path not in allowed:
            errors.append(f"{op.op_id}: scope_undeclared_target: {op.path}")
    if not allowed and contract.scope_policy_result == "scope_allowed_with_warning":
        if len(set(op.path for op in operations)) > 3:
            errors.append("scope_too_broad: warning-scope operation plan exceeds bootstrap budget")
    elif len(allowed) > 0 and len(set(op.path for op in operations)) > len(allowed):
        errors.append("scope_too_broad: operation plan exceeds editable target budget")
    return not errors, errors

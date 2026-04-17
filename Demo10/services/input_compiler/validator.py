from __future__ import annotations
from typing import List, Optional
from .models import CompiledSpecIR, CompileStatus, OperationType, OperationIR
from .issues import (
    CompileIssue, MISSING_TITLE, MISSING_OBJECTIVE, NO_SUPPORTED_OPERATION,
    MISSING_REQUIRED_TARGET, AMBIGUOUS_TARGET_FILE, CONFLICTING_ACTIONS,
    INFERRED_TITLE, VAGUE_WORDING
)

class InputValidator:
    def validate(self, ir: CompiledSpecIR) -> List[CompileIssue]:
        issues = []

        # Title present
        if not ir.title or ir.title.strip() == "":
            issues.append(CompileIssue(
                severity="error",
                code=MISSING_TITLE,
                message="Spec title is missing",
                field="title"
            ))
        elif ir.original_text.startswith(ir.title):
            # Example of warning if inferred from first line
            pass

        # Objective present
        if not ir.objective or ir.objective.strip() == "":
            issues.append(CompileIssue(
                severity="error",
                code=MISSING_OBJECTIVE,
                message="Spec objective is missing",
                field="objective"
            ))

        # At least one operation present
        if not ir.operations:
            issues.append(CompileIssue(
                severity="error",
                code=NO_SUPPORTED_OPERATION,
                message="At least one supported operation must be present",
                field="operations"
            ))

        if ir.defaults_applied:
            issues.append(CompileIssue(
                severity="warning",
                code="DEFAULTS_APPLIED",
                message=f"Deterministic defaults applied: {', '.join(ir.defaults_applied)}"
            ))

        # Validate each operation
        for i, op in enumerate(ir.operations):
            # File-targeted ops have target path when required
            if op.op_type in [OperationType.CREATE_FILE, OperationType.MODIFY_FILE, OperationType.WRITE_SPEC]:
                if not op.target or op.target.strip() == "":
                    issues.append(CompileIssue(
                        severity="error",
                        code=MISSING_REQUIRED_TARGET,
                        message=f"Operation {i+1} ({op.op_type.value}) requires a target path",
                        field=f"operations[{i}].target",
                        repairable=True,
                        repair_type="provide_value"
                    ))

            if "vague" in op.instruction.lower():
                issues.append(CompileIssue(
                    severity="warning",
                    code=VAGUE_WORDING,
                    message=f"Operation {i+1} has vague instructions",
                    field=f"operations[{i}].instruction"
                ))

        # Check for conflicting actions (simplified: same target, different instructions that might conflict)
        targets = {}
        for op in ir.operations:
            if op.target:
                if op.target in targets:
                    prev_op = targets[op.target]
                    combined_instr = (prev_op.instruction + " " + op.instruction).lower()
                    # In a real scenario, we'd check if they truly conflict.
                    # For this spec, we'll just demonstrate the check.
                    if "delete" in combined_instr and "keep" in combined_instr:
                        issues.append(CompileIssue(
                            severity="error",
                            code=CONFLICTING_ACTIONS,
                            message=f"Conflicting actions detected for target {op.target}",
                            field="operations"
                        ))
                targets[op.target] = op

        return issues

    def evaluate_eligibility(self, issues: List[CompileIssue]) -> CompileStatus:
        if any(issue.severity == "error" for issue in issues):
            return CompileStatus.BLOCKED
        if any(issue.severity == "warning" for issue in issues):
            return CompileStatus.COMPILED_WITH_WARNINGS
        return CompileStatus.COMPILED_CLEAN

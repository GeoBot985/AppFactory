from __future__ import annotations

import re
from typing import Optional
from .models import (
    EditInstruction, EditResult, EditStatus, AnchorStatus,
    OperationType, AnchorType, IdempotencyRecord, ChangeSummary,
    AnchorResolution
)
from .anchor_resolver import AnchorResolver
from .idempotency import is_content_equivalent, is_import_equivalent


class EditEngine:
    def __init__(self, resolver: AnchorResolver):
        self.resolver = resolver

    def apply(self, lines: list[str], instruction: EditInstruction) -> tuple[list[str], EditResult]:
        res = self.resolver.resolve(lines, instruction.anchor_type, instruction.anchor_value, instruction.match_mode)

        op = instruction.operation

        # Check constraints
        # Some operations (ensure, append) don't fail if anchor is missing
        requires_anchor = op in [
            OperationType.INSERT_BEFORE,
            OperationType.INSERT_AFTER,
            OperationType.REPLACE_BLOCK,
            OperationType.DELETE_BLOCK
        ]

        if requires_anchor and instruction.constraints.fail_if_missing and res.status == AnchorStatus.NOT_FOUND:
            return lines, self._fail(instruction, res, "Anchor not found")

        if instruction.constraints.fail_if_multiple and res.status == AnchorStatus.AMBIGUOUS:
            return lines, self._fail(instruction, res, "Ambiguous anchor")

        if op == OperationType.INSERT_BEFORE:
            return self._insert(lines, instruction, res, before=True)
        if op == OperationType.INSERT_AFTER:
            return self._insert(lines, instruction, res, before=False)
        if op == OperationType.REPLACE_BLOCK:
            return self._replace(lines, instruction, res)
        if op == OperationType.APPEND_IF_MISSING:
            return self._append_if_missing(lines, instruction)
        if op == OperationType.ENSURE_IMPORT:
            return self._ensure_import(lines, instruction)
        if op == OperationType.ENSURE_FUNCTION:
            return self._ensure_symbol(lines, instruction, "def")
        if op == OperationType.ENSURE_CLASS:
            return self._ensure_symbol(lines, instruction, "class")
        if op == OperationType.DELETE_BLOCK:
            return self._delete(lines, instruction, res)

        return lines, self._fail(instruction, res, f"Unsupported operation: {op}")

    def _insert(self, lines: list[str], inst: EditInstruction, res: AnchorResolution, before: bool) -> tuple[list[str], EditResult]:
        if not res.selected_match:
            return lines, self._fail(inst, res, "No match selected for insertion")

        idx = res.selected_match.start_line if before else res.selected_match.end_line + 1
        new_payload = inst.payload
        if not new_payload.endswith("\n"):
            new_payload += "\n"

        payload_lines = new_payload.splitlines(keepends=True)
        new_lines = lines[:idx] + payload_lines + lines[idx:]

        return new_lines, self._success(inst, res, lines, new_lines, "Inserted payload")

    def _replace(self, lines: list[str], inst: EditInstruction, res: AnchorResolution) -> tuple[list[str], EditResult]:
        if not res.selected_match:
            return lines, self._fail(inst, res, "No match selected for replacement")

        start = res.selected_match.start_line
        end = res.selected_match.end_line

        new_payload = inst.payload
        if not new_payload.endswith("\n"):
            new_payload += "\n"
        payload_lines = new_payload.splitlines(keepends=True)

        # Idempotency check: if existing block is equivalent to payload, skip
        existing_block = "".join(lines[start : end + 1])
        if is_content_equivalent(existing_block, inst.payload):
            return lines, self._no_op(inst, res, "Content already matches")

        new_lines = lines[:start] + payload_lines + lines[end + 1:]
        return new_lines, self._success(inst, res, lines, new_lines, "Replaced block")

    def _append_if_missing(self, lines: list[str], inst: EditInstruction) -> tuple[list[str], EditResult]:
        content = "".join(lines)
        if inst.payload in content or is_content_equivalent(inst.payload, content):
             # Actually, "in content" might be too loose, but append_if_missing usually means "ensure this block exists"
             # Let's check if the normalized payload exists as a block
             if self._contains_normalized(lines, inst.payload):
                 return lines, self._no_op(inst, AnchorResolution(status=AnchorStatus.OK), "Payload already exists")

        new_payload = inst.payload
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        if not new_payload.endswith("\n"):
            new_payload += "\n"

        new_lines = lines + new_payload.splitlines(keepends=True)
        return new_lines, self._success(inst, AnchorResolution(status=AnchorStatus.OK), lines, new_lines, "Appended payload")

    def _contains_normalized(self, lines: list[str], payload: str) -> bool:
        full_text = "".join(lines)
        # Simple check for now:
        return payload.strip() in full_text

    def _ensure_import(self, lines: list[str], inst: EditInstruction) -> tuple[list[str], EditResult]:
        for i, line in enumerate(lines):
            if is_import_equivalent(line, inst.payload):
                return lines, self._no_op(inst, AnchorResolution(status=AnchorStatus.OK), "Import already exists")

        # Find where to insert: after last import or at start
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.strip().startswith(("import ", "from ")):
                insert_idx = i + 1

        new_payload = inst.payload.strip() + "\n"
        new_lines = lines[:insert_idx] + [new_payload] + lines[insert_idx:]
        return new_lines, self._success(inst, AnchorResolution(status=AnchorStatus.OK), lines, new_lines, "Import added")

    def _ensure_symbol(self, lines: list[str], inst: EditInstruction, keyword: str) -> tuple[list[str], EditResult]:
        # Reuse resolve to see if it exists
        res = self.resolver.resolve(lines, AnchorType.FUNCTION if keyword == "def" else AnchorType.CLASS, inst.anchor_value)

        mode = inst.constraints.ensure_mode
        if res.status == AnchorStatus.OK:
            if mode == "create_only":
                return lines, self._no_op(inst, res, f"{keyword} {inst.anchor_value} already exists")
            elif mode == "replace_if_exists":
                return self._replace(lines, inst, res)
            elif mode == "fail_if_exists":
                return lines, self._fail(inst, res, f"{keyword} {inst.anchor_value} already exists")

        # If missing, append
        return self._append_if_missing(lines, inst)

    def _delete(self, lines: list[str], inst: EditInstruction, res: AnchorResolution) -> tuple[list[str], EditResult]:
        if not res.selected_match:
            return lines, self._fail(inst, res, "No match selected for deletion")

        start = res.selected_match.start_line
        end = res.selected_match.end_line
        new_lines = lines[:start] + lines[end + 1:]
        return new_lines, self._success(inst, res, lines, new_lines, "Deleted block")

    def _fail(self, inst: EditInstruction, res: AnchorResolution, reason: str) -> EditResult:
        return EditResult(
            task_id=inst.task_id,
            file_path=inst.file_path,
            status=EditStatus.FAILED,
            operation=inst.operation,
            anchor_resolution=res,
            reason=reason
        )

    def _no_op(self, inst: EditInstruction, res: AnchorResolution, reason: str) -> EditResult:
         return EditResult(
            task_id=inst.task_id,
            file_path=inst.file_path,
            status=EditStatus.NO_OP,
            operation=inst.operation,
            anchor_resolution=res,
            reason=reason,
            idempotency_check=IdempotencyRecord(status="skipped_existing", reason=reason)
        )

    def _success(self, inst: EditInstruction, res: AnchorResolution, old_lines: list[str], new_lines: list[str], reason: str) -> EditResult:
        summary = ChangeSummary(
            lines_before=len(old_lines),
            lines_after=len(new_lines),
            delta=len(new_lines) - len(old_lines)
        )
        return EditResult(
            task_id=inst.task_id,
            file_path=inst.file_path,
            status=EditStatus.APPLIED,
            operation=inst.operation,
            anchor_resolution=res,
            change_summary=summary,
            reason=reason,
            preview_before=res.selected_match.preview if res.selected_match else "",
            preview_after=inst.payload if inst.operation != OperationType.DELETE_BLOCK else "",
            idempotency_check=IdempotencyRecord(status="applied", reason=reason)
        )

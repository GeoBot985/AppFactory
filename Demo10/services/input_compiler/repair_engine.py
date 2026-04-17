from __future__ import annotations
import copy
from typing import Any, Dict, List
from .models import CompiledSpecIR, OperationIR, OperationType
from .repair_models import RepairAction

class RepairEngine:
    def apply_repair(self, ir: CompiledSpecIR, action: RepairAction) -> CompiledSpecIR:
        """Applies a repair action to the IR. Returns a new modified IR."""
        updated_ir = copy.deepcopy(ir)

        # Simple field path resolver
        # For Demo10, target_field might be "title", "objective", or "operations[0].target"

        if action.action_type == "set_field" or action.action_type == "select_from_candidates" or action.action_type == "add_missing_field":
            self._set_ir_field(updated_ir, action.target_field, action.value)

        elif action.action_type == "remove_operation":
            self._remove_ir_operation(updated_ir, action.target_field)

        elif action.action_type == "replace_operation":
            self._replace_ir_operation(updated_ir, action.target_field, action.value)

        return updated_ir

    def _set_ir_field(self, ir: CompiledSpecIR, field_path: str, value: Any):
        if field_path == "title":
            ir.title = value
        elif field_path == "objective":
            ir.objective = value
        elif field_path == "target_path":
            ir.target_path = value
        elif field_path.startswith("operations["):
            # Format: operations[index].field
            try:
                parts = field_path.split(".")
                idx_part = parts[0].split("[")[1].split("]")[0]
                idx = int(idx_part)
                field = parts[1]
                if idx < len(ir.operations):
                    if field == "target":
                        ir.operations[idx].target = value
                    elif field == "instruction":
                        ir.operations[idx].instruction = value
            except (IndexError, ValueError):
                pass

    def _remove_ir_operation(self, ir: CompiledSpecIR, field_path: str):
        if field_path == "operations":
            # If no index, maybe remove the first one or we expect an index
            pass
        elif field_path.startswith("operations["):
            try:
                idx_part = field_path.split("[")[1].split("]")[0]
                idx = int(idx_part)
                if idx < len(ir.operations):
                    ir.operations.pop(idx)
            except (IndexError, ValueError):
                pass

    def _replace_ir_operation(self, ir: CompiledSpecIR, field_path: str, value: Any):
        # value here is likely the new OperationType
        if field_path.startswith("operations["):
            try:
                idx_part = field_path.split("[")[1].split("]")[0]
                idx = int(idx_part)
                if idx < len(ir.operations):
                    try:
                        ir.operations[idx].op_type = OperationType(value)
                    except ValueError:
                        pass
            except (IndexError, ValueError):
                pass
        elif field_path == "operations":
            # Special case for NO_SUPPORTED_OPERATION where we might want to add a fresh one if empty
            if not ir.operations:
                try:
                    ir.operations.append(OperationIR(
                        op_type=OperationType(value),
                        target="",
                        instruction="New operation from repair"
                    ))
                except ValueError:
                    pass

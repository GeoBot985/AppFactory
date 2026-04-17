from __future__ import annotations
import re
from datetime import datetime
from typing import List, Tuple, Optional

from .context_snapshot import ContextSnapshot
from ..input_compiler.models import CompiledSpecIR, OperationIR, OperationType
from ..input_compiler.issues import (
    AUTO_TARGET_FILENAME, DEFAULT_DIRECTORY, NEXT_SPEC_RESOLUTION,
    SINGLE_CANDIDATE_RESOLVED, RECENT_FILE_INFERRED, WORKSPACE_ROOT_NORMALIZED
)

def apply_rule_1_missing_target_file(ir: CompiledSpecIR, context: ContextSnapshot) -> List[str]:
    """Rule 1 — Missing target file (create_file)"""
    defaults = []
    for op in ir.operations:
        if op.op_type == OperationType.CREATE_FILE and not op.target:
            # Generate filename from title
            safe_title = re.sub(r"[^a-z0-9]+", "_", ir.title.lower()).strip("_")
            if not safe_title:
                safe_title = f"artifact_{int(datetime.now().timestamp())}"

            # Guess extension based on instructions or defaults to .py
            ext = ".py"
            if "markdown" in op.instruction.lower() or "document" in op.instruction.lower():
                ext = ".md"

            op.target = f"{safe_title}{ext}"
            ir.assumptions.append(f"target filename auto-generated from title: {op.target}")
            ir.warnings.append(f"[{AUTO_TARGET_FILENAME}] Operation target defaulted to {op.target}")
            defaults.append("RULE_001_AUTO_TARGET_FILENAME")
    return defaults

def apply_rule_2_missing_directory(ir: CompiledSpecIR, context: ContextSnapshot) -> List[str]:
    """Rule 2 — Missing directory"""
    defaults = []
    for op in ir.operations:
        if op.target and "/" not in op.target and "\\" not in op.target:
            # No directory specified, use active_directory
            # But only if it's not already at the root or we want to be explicit
            # For this rule, we just log the assumption if we were to prepend it
            # But the requirement says "use active_directory"
            if context.active_directory != ".":
                op.target = f"{context.active_directory}/{op.target}"
                ir.assumptions.append(f"target directory defaulted to active workspace: {context.active_directory}")
                ir.warnings.append(f"[{DEFAULT_DIRECTORY}] Target directory defaulted to {context.active_directory}")
                defaults.append("RULE_002_DEFAULT_DIRECTORY")
    return defaults

def apply_rule_3_next_spec_resolution(ir: CompiledSpecIR, context: ContextSnapshot) -> List[str]:
    """Rule 3 — “next spec” resolution"""
    defaults = []
    for op in ir.operations:
        if op.op_type == OperationType.WRITE_SPEC:
            if not op.target or "next" in op.target.lower():
                next_num = (context.last_spec_number or 0) + 1
                op.target = f"spec_{next_num:03d}.md"
                ir.assumptions.append(f"resolved next spec number = {next_num}")
                ir.warnings.append(f"[{NEXT_SPEC_RESOLUTION}] Resolved next spec as {op.target}")
                defaults.append("RULE_003_NEXT_SPEC_RESOLUTION")
    return defaults

def apply_rule_4_single_candidate_disambiguation(ir: CompiledSpecIR, context: ContextSnapshot) -> List[str]:
    """Rule 4 — Single candidate disambiguation"""
    defaults = []
    for op in ir.operations:
        if op.target and op.target not in context.files:
            # Check if it matches exactly one file in the workspace
            candidates = [f for f in context.files if op.target in f]
            if len(candidates) == 1:
                old_target = op.target
                op.target = candidates[0]
                ir.assumptions.append(f"resolved ambiguous reference '{old_target}' to '{op.target}'")
                ir.warnings.append(f"[{SINGLE_CANDIDATE_RESOLVED}] Ambiguous reference auto-resolved to {op.target}")
                defaults.append("RULE_004_SINGLE_CANDIDATE_DISAMBIGUATION")
    return defaults

def apply_rule_5_default_operation_target_from_recent_context(ir: CompiledSpecIR, context: ContextSnapshot) -> List[str]:
    """Rule 5 — Default operation target from recent context"""
    defaults = []
    if len(context.recent_files) == 1:
        recent_file = context.recent_files[0]
        for op in ir.operations:
            if not op.target and op.op_type in [OperationType.MODIFY_FILE, OperationType.ANALYZE_CODEBASE]:
                # Rule 5 — Non-Auto-Fill Cases (Strict): do not auto-fill if destructive intent present
                instr = op.instruction.lower()
                if any(word in instr for word in ["delete", "remove", "overwrite", "erase", "format"]):
                    continue

                op.target = recent_file
                ir.assumptions.append(f"target inferred from most recent file: {recent_file}")
                ir.warnings.append(f"[{RECENT_FILE_INFERRED}] Target inferred from recent context: {recent_file}")
                defaults.append("RULE_005_RECENT_FILE_INFERENCE")
    return defaults

def apply_rule_6_normalize_current_project(ir: CompiledSpecIR, context: ContextSnapshot) -> List[str]:
    """Rule 6 — Normalize “current project”"""
    defaults = []
    keywords = ["this project", "current app", "demo"]
    if ir.target_path and any(k in ir.target_path.lower() for k in keywords):
        ir.target_path = context.workspace_root
        ir.assumptions.append(f"normalized '{ir.target_path}' to workspace root")
        ir.warnings.append(f"[{WORKSPACE_ROOT_NORMALIZED}] Normalized target path to workspace root")
        defaults.append("RULE_006_NORMALIZE_CURRENT_PROJECT")

    for op in ir.operations:
        if op.target and any(k in op.target.lower() for k in keywords):
            op.target = context.workspace_root
            ir.assumptions.append(f"normalized operation target to workspace root")
            defaults.append("RULE_006_NORMALIZE_CURRENT_PROJECT")
    return defaults

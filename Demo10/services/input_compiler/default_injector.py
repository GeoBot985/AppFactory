from __future__ import annotations
from typing import List

from .models import CompiledSpecIR
from ..context.context_snapshot import ContextSnapshot
from ..context.default_rules import (
    apply_rule_1_missing_target_file,
    apply_rule_2_missing_directory,
    apply_rule_3_next_spec_resolution,
    apply_rule_4_single_candidate_disambiguation,
    apply_rule_5_default_operation_target_from_recent_context,
    apply_rule_6_normalize_current_project
)

class DefaultInjector:
    def inject_defaults(self, ir: CompiledSpecIR, context: ContextSnapshot) -> CompiledSpecIR:
        # Rules should be applied in a deterministic order
        applied_rules = []

        applied_rules.extend(apply_rule_6_normalize_current_project(ir, context))
        applied_rules.extend(apply_rule_3_next_spec_resolution(ir, context))
        applied_rules.extend(apply_rule_1_missing_target_file(ir, context))
        applied_rules.extend(apply_rule_5_default_operation_target_from_recent_context(ir, context))
        applied_rules.extend(apply_rule_4_single_candidate_disambiguation(ir, context))
        applied_rules.extend(apply_rule_2_missing_directory(ir, context))

        # Deduplicate applied rules
        ir.defaults_applied = sorted(list(set(applied_rules)))

        return ir

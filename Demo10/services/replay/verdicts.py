from typing import Literal
from .models import ReplayComparison

class VerdictEngine:
    def determine_verdict(self, comparison: ReplayComparison) -> Literal[
        "exact_match",
        "structural_match",
        "outcome_match",
        "mismatch",
        "not_comparable"
    ]:
        if not comparison.plan_match:
            return "mismatch"

        if not comparison.step_order_match or not comparison.step_count_match:
            return "mismatch"

        if comparison.status_match and comparison.outputs_match and comparison.rollback_match:
            # We also check for retry count warnings? requirements say exact match includes retries
            retry_mismatches = [m for m in comparison.mismatches if m.category == "retry_count"]
            if not retry_mismatches:
                return "exact_match"
            else:
                return "structural_match"

        if comparison.status_match and comparison.rollback_match:
            return "structural_match"

        # If final statuses of source run and replay run match but internal trace differs
        # Wait, comparison.status_match is source_run.status == replay_run.status
        # Requirement: outcome_match = Final outcome matches, but internal trace differs.

        # If we have any status mismatches on steps, but the overall run status matches
        if comparison.status_match:
             return "outcome_match"

        return "mismatch"

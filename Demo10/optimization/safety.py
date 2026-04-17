from typing import List
from .models import OptimizationCandidate

class SafetyVerifier:
    def verify_safety(self, candidate: OptimizationCandidate) -> bool:
        contract = candidate.safety_contract

        # In v1, we strictly enforce these booleans
        if not all([
            contract.preserves_step_order_semantics,
            contract.preserves_outputs,
            contract.preserves_retry_boundaries,
            contract.preserves_rollback_behavior,
            contract.preserves_verification_comparability
        ]):
            return False

        # Additional checks based on optimization type
        if candidate.optimization_type == "duplicate_elimination":
            return "No mutation on target between original validations" in contract.explicit_conditions

        if candidate.optimization_type == "io_collapse":
            return "Target written and then read immediately" in contract.explicit_conditions

        if candidate.optimization_type == "validation_collapse":
            return "Stronger validation follows weaker one" in contract.explicit_conditions

        return True

    def get_unsafe_reason(self, candidate: OptimizationCandidate) -> str:
        contract = candidate.safety_contract
        if not contract.preserves_step_order_semantics:
            return "Changes step order semantics"
        if not contract.preserves_outputs:
            return "Changes observable outputs"
        if not contract.preserves_retry_boundaries:
            return "Changes retry boundaries"
        if not contract.preserves_rollback_behavior:
            return "Changes rollback behavior"
        if not contract.preserves_verification_comparability:
            return "Breaks verification comparability"

        return "Safety conditions not met"

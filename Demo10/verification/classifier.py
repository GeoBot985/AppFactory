from typing import List, Literal, Dict, Any
from .models import GoldenRunResult, DriftCategory
from Demo10.services.replay.models import ReplayResult

class VerificationClassifier:
    def classify(self, golden_run_id: str, replay_result: ReplayResult) -> GoldenRunResult:
        verdict = replay_result.reproducibility_verdict

        # Mapping from Spec 049:
        # Replay Verdict    Classification
        # exact_match       pass
        # structural_match    pass
        # outcome_match       warn
        # mismatch          fail
        # not_comparable    warn or fail (we'll use fail for strictness)

        classification: Literal["pass", "warn", "fail"] = "fail"
        if verdict == "exact_match":
            classification = "pass"
        elif verdict == "structural_match":
            classification = "pass"
        elif verdict == "outcome_match":
            classification = "warn"
        elif verdict == "mismatch":
            classification = "fail"
        else:
            classification = "fail"

        drift_categories = self._identify_drift(replay_result)

        return GoldenRunResult(
            golden_run_id=golden_run_id,
            replay_result=replay_result,
            verdict=verdict if verdict in ["exact_match", "structural_match", "outcome_match", "fail"] else "fail",
            classification=classification,
            drift_categories=drift_categories
        )

    def _identify_drift(self, replay_result: ReplayResult) -> List[str]:
        drift = []
        comp = replay_result.comparison

        if not comp.plan_match:
            drift.append("plan_drift")

        # execution_drift: step order, step count, or step status mismatch
        if not comp.step_order_match or not comp.step_count_match:
            drift.append("execution_drift")

        has_status_mismatch = any(m.category == "step_status" for m in comp.mismatches)
        if has_status_mismatch:
            drift.append("execution_drift")

        if any(m.category == "retry_count" for m in comp.mismatches):
            drift.append("retry_drift")

        if not comp.rollback_match:
            drift.append("rollback_drift")

        if not comp.outputs_match:
            drift.append("output_drift")

        # environment_drift is harder to detect from ReplayResult currently
        # unless it was recorded in mismatches

        return drift

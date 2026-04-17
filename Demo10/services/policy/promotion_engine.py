from datetime import datetime
from typing import List, Optional, Tuple, Any, Dict
from .models import (
    PromotionCandidate,
    PromotionDecision,
    PromotionPolicy,
    EnvironmentPolicy,
    Environment
)
from .audit import PromotionAuditService
from Demo10.verification.models import VerificationResult, GoldenRunResult
import dataclasses
from telemetry.events import TelemetryEmitter
from pathlib import Path

class PromotionEngine:
    def __init__(self, policy: PromotionPolicy, audit_service: PromotionAuditService, workspace_root: Optional[Path] = None):
        self.policy = policy
        self.audit_service = audit_service
        self.telemetry = TelemetryEmitter(workspace_root) if workspace_root else None

    def evaluate_promotion(self, candidate: PromotionCandidate, verification_result: VerificationResult) -> PromotionDecision:
        env_policy = self.policy.environment_rules.get(candidate.target_environment)
        if not env_policy:
            return PromotionDecision(
                candidate_id=candidate.candidate_id,
                decision="rejected",
                reasons=[f"No policy defined for environment: {candidate.target_environment}"],
                policy_snapshot={},
                evaluated_at=datetime.now()
            )

        reasons = []

        # Rule 1 — Overall Verdict
        if verification_result.overall_verdict == "fail":
            reasons.append("PROMOTION_REJECTED_VERDICT: overall verdict is fail")
        elif env_policy.required_verdict == "pass" and verification_result.overall_verdict == "pass_with_warnings":
            reasons.append("PROMOTION_REJECTED_VERDICT: target environment requires exact pass, but got warnings")

        # Rule 2 — Warnings
        warn_count = verification_result.summary.get("warn_count", 0)
        if not env_policy.allow_warn and warn_count > 0:
            reasons.append("PROMOTION_REJECTED_WARNINGS: warnings not allowed in target environment")

        # Rule 3 — Not Comparable
        has_not_comparable = any(res.verdict == "fail" for res in verification_result.run_results) # simplified
        # Actually SPEC 049 models GoldenRunResult has verdict: Literal["exact_match", "structural_match", "outcome_match", "fail"]
        # and classification: Literal["pass", "warn", "fail"]
        # SPEC 050 mentions "allow_not_comparable". Usually "fail" in verdict might mean not comparable or just different.
        # Let's assume if any run is 'fail' it might be not comparable or a failure.

        # Re-reading Rule 3: "allow_not_comparable = False AND any(not_comparable) -> reject"
        # Since I don't see an explicit "not_comparable" flag in GoldenRunResult, I'll infer it from verdict or classification
        # if appropriate, or check if VerificationResult summary has it.
        if not env_policy.allow_not_comparable:
             # In some systems, not comparable is distinct from fail.
             # For now, let's check if the verdict was 'fail' which often implies it couldn't be compared.
             if any(res.verdict == "fail" for res in verification_result.run_results):
                 reasons.append("PROMOTION_REJECTED_NOT_COMPARABLE: verification contains non-comparable runs")

        # Rule 4 — Drift Categories
        found_drifts = set()
        for res in verification_result.run_results:
            found_drifts.update(res.drift_categories)

        blocked_drifts = set(env_policy.blocked_drift_categories)
        intersect = found_drifts.intersection(blocked_drifts)
        if intersect:
            reasons.append(f"PROMOTION_REJECTED_DRIFT: blocked drift categories found: {list(intersect)}")

        # Rule 5 — Failure Count
        fail_count = verification_result.summary.get("fail_count", 0)
        if fail_count > env_policy.max_failures:
            reasons.append(f"PROMOTION_REJECTED_FAILURE_COUNT: failure count {fail_count} exceeds maximum {env_policy.max_failures}")

        # Rule 6 — Exact Match
        if env_policy.require_exact_match:
            if any(res.verdict != "exact_match" for res in verification_result.run_results):
                reasons.append("PROMOTION_REJECTED_EXACT_MATCH: exact match required but not met")

        decision_str = "approved"
        if reasons:
            decision_str = "rejected"
        elif verification_result.overall_verdict == "pass_with_warnings":
            decision_str = "approved_with_warnings"

        return PromotionDecision(
            candidate_id=candidate.candidate_id,
            decision=decision_str,
            reasons=reasons,
            policy_snapshot=dataclasses.asdict(env_policy),
            evaluated_at=datetime.now()
        )

    def promote(self, candidate: PromotionCandidate, verification_result: VerificationResult) -> PromotionDecision:
        decision = self.evaluate_promotion(candidate, verification_result)

        if self.telemetry:
             self.telemetry.emit("promotion_decision", {
                 "candidate_id": candidate.candidate_id,
                 "target_environment": candidate.target_environment,
                 "decision": decision.decision,
                 "system_version": candidate.system_version
             })

        candidate_info = {
            "source_environment": candidate.source_environment,
            "target_environment": candidate.target_environment,
            "system_version": candidate.system_version,
            "verification_suite_id": candidate.verification_suite_id,
            "verification_result_id": candidate.verification_result_id
        }

        self.audit_service.record_decision(decision, candidate_info)
        return decision

    def override_promotion(self, candidate: PromotionCandidate, verification_result: VerificationResult, reason: str) -> PromotionDecision:
        # Evaluate anyway to see what the original decision would have been
        original_decision = self.evaluate_promotion(candidate, verification_result)

        override_decision = PromotionDecision(
            candidate_id=candidate.candidate_id,
            decision="approved_with_override",
            reasons=original_decision.reasons + [f"MANUAL_OVERRIDE: {reason}"],
            policy_snapshot=original_decision.policy_snapshot,
            evaluated_at=datetime.now()
        )

        if self.telemetry:
            self.telemetry.emit("promotion_decision", {
                "candidate_id": candidate.candidate_id,
                "target_environment": candidate.target_environment,
                "decision": override_decision.decision,
                "system_version": candidate.system_version,
                "is_override": True
            })

        candidate_info = {
            "source_environment": candidate.source_environment,
            "target_environment": candidate.target_environment,
            "system_version": candidate.system_version,
            "verification_suite_id": candidate.verification_suite_id,
            "verification_result_id": candidate.verification_result_id
        }

        self.audit_service.record_decision(override_decision, candidate_info)
        return override_decision

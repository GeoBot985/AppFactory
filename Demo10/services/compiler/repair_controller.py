from __future__ import annotations
import uuid
import copy
from typing import List, Dict, Any, Tuple, Optional
from services.draft_spec.models import DraftSpec
from .models import CompileReport, CompileStatus, CompileDiagnostic, DiagnosticSeverity
from .repair_models import CompileRepairSession, CompileRepairAttempt, RepairStatus, RepairConfidence
from .repair_strategies import RepairStrategies
from .error_classifier import ErrorClassifier
from services.policy.engine import PolicyEngine
from services.policy.models import PolicyDomain, PolicyDecision

class RepairController:
    def __init__(self, strategies: RepairStrategies, policy_engine: PolicyEngine):
        self.strategies = strategies
        self.policy_engine = policy_engine

    def run_repair_loop(self, draft: DraftSpec, compile_func: Any, max_attempts: int = 3, session_context: Optional[Dict[str, Any]] = None) -> Tuple[DraftSpec, CompileRepairSession]:
        session = CompileRepairSession(
            session_id=f"repair_{uuid.uuid4().hex[:8]}",
            draft_id=draft.draft_id,
            max_attempts=max_attempts
        )

        current_draft = copy.deepcopy(draft)

        for i in range(max_attempts):
            # Compile current version
            plan, report = compile_func(current_draft)

            if report.status == CompileStatus.SUCCESS:
                session.final_status = RepairStatus.SUCCESS
                return current_draft, session

            # If failed, attempt repair
            attempt = CompileRepairAttempt(
                attempt_id=i + 1,
                confidence=RepairConfidence.MEDIUM, # Default
                reason="auto_repair_cycle"
            )

            # 1. Deterministic repairs
            det_changes, det_fixed = self.strategies.apply_deterministic_repairs(current_draft, report.errors)
            if det_changes:
                attempt.changes.extend(det_changes)
                attempt.errors_fixed.extend(det_fixed)
                attempt.confidence = RepairConfidence.HIGH
                attempt.reason = "deterministic_fix"

            # 2. LLM repairs (if deterministic didn't fix everything or as second stage)
            remaining_errors = [e for e in report.errors if e.code not in attempt.errors_fixed]
            if remaining_errors:
                llm_changes, llm_fixed = self.strategies.apply_llm_repairs(current_draft, remaining_errors, session_context)
                if llm_changes:
                    attempt.changes.extend(llm_changes)
                    attempt.errors_fixed.extend(llm_fixed)
                    # Mix of deterministic and LLM might lower confidence to MEDIUM if it wasn't already HIGH
                    if attempt.reason == "deterministic_fix":
                        attempt.reason = "mixed_fix"
                        attempt.confidence = RepairConfidence.MEDIUM
                    else:
                        attempt.reason = "llm_inference"
                        attempt.confidence = RepairConfidence.LOW

            if not attempt.changes:
                attempt.status = RepairStatus.FAILED
                session.attempts.append(attempt)
                session.final_status = RepairStatus.FAILED
                break # No more repairs possible

            # 3. Policy Check on Repaired Draft
            policy_context = {
                "repair_attempt": attempt.attempt_id,
                "changes_count": len(attempt.changes),
                "fixed_errors_count": len(attempt.errors_fixed)
            }
            policy_result = self.policy_engine.evaluate(PolicyDomain.COMPILE, f"repair_{session.session_id}", policy_context)

            if policy_result.decision == PolicyDecision.BLOCK.value:
                attempt.status = RepairStatus.ABORTED
                attempt.reason += f" (Policy Blocked: {', '.join(policy_result.reasons)})"
                session.attempts.append(attempt)
                session.final_status = RepairStatus.ABORTED
                break

            attempt.status = RepairStatus.SUCCESS
            session.attempts.append(attempt)

        if session.final_status == RepairStatus.PENDING:
             session.final_status = RepairStatus.FAILED # Reached max attempts without success

        return current_draft, session

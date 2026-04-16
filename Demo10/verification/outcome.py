from __future__ import annotations
from typing import List, Optional, Any
from .models import FinalOutcome, FailureStage, CheckStatus, Severity, VerificationReport, RunSummary

class OutcomeSynthesizer:
    def synthesize(
        self,
        spec_id: str,
        tasks: List[Any],
        verification_report: VerificationReport,
        failure_stage: Optional[FailureStage] = None,
        regression_status: Any = None
    ) -> RunSummary:

        tasks_total = len(tasks)
        tasks_failed = sum(1 for t in tasks if hasattr(t, 'status') and (t.status.value if hasattr(t.status, 'value') else str(t.status)) == "failed")
        # In this context, we'll assume COMPLETED tasks with non-empty changes are 'applied'
        tasks_applied = sum(1 for t in tasks if hasattr(t, 'status') and (t.status.value if hasattr(t.status, 'value') else str(t.status)) == "completed" and getattr(t.result, 'changes', []))
        tasks_no_op = tasks_total - tasks_failed - tasks_applied

        # Determine final status and failure stage
        final_status = FinalOutcome.COMPLETED

        if failure_stage:
            if failure_stage in {FailureStage.SPEC_FAILURE, FailureStage.PLANNER_FAILURE}:
                final_status = FinalOutcome.FAILED
            elif failure_stage in {FailureStage.EDIT_FAILURE, FailureStage.STRUCTURAL_VALIDATION_FAILURE}:
                final_status = FinalOutcome.PARTIAL_FAILURE
        elif tasks_failed > 0:
            final_status = FinalOutcome.PARTIAL_FAILURE
            failure_stage = FailureStage.EDIT_FAILURE

        # Verification impact
        if final_status not in {FinalOutcome.FAILED}:
            has_hard_fail = any(c.status in {CheckStatus.FAIL, CheckStatus.ERROR} and c.severity == Severity.HARD for c in verification_report.checks)
            has_soft_fail = any(c.status in {CheckStatus.FAIL, CheckStatus.ERROR, CheckStatus.WARN} and c.severity == Severity.SOFT for c in verification_report.checks)

            if has_hard_fail:
                final_status = FinalOutcome.PARTIAL_FAILURE
                failure_stage = FailureStage.VERIFICATION_FAILURE
            elif has_soft_fail:
                final_status = FinalOutcome.COMPLETED_WITH_WARNINGS

        # Regression impact
        if regression_status and regression_status.get("status") == "fail":
             final_status = FinalOutcome.PARTIAL_FAILURE # or keep existing if already worse
             if not failure_stage: failure_stage = FailureStage.REGRESSION_FAILURE

        return RunSummary(
            spec_id=spec_id,
            mode="dsl", # assumed for now
            tasks_total=tasks_total,
            tasks_applied=tasks_applied,
            tasks_no_op=tasks_no_op,
            tasks_failed=tasks_failed,
            verification=verification_report.summary,
            regression=regression_status or {"enabled": False},
            final_status=final_status,
            failure_stage=failure_stage,
            summary=self._generate_summary_text(final_status, failure_stage, verification_report)
        )

    def _generate_summary_text(self, status: FinalOutcome, stage: Optional[FailureStage], report: VerificationReport) -> str:
        if status == FinalOutcome.COMPLETED:
            return "Execution succeeded and all verification checks passed."
        if status == FinalOutcome.COMPLETED_WITH_WARNINGS:
            return "Execution succeeded but soft verification warnings occurred."
        if status == FinalOutcome.PARTIAL_FAILURE:
            msg = f"Partial failure at {stage.value if stage else 'UNKNOWN'} stage."
            if report.summary.get("failed", 0) > 0:
                msg += f" {report.summary['failed']} verification checks failed."
            return msg
        if status == FinalOutcome.FAILED:
            return f"Critical failure at {stage.value if stage else 'UNKNOWN'} stage."
        return "Unknown outcome."

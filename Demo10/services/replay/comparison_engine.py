from typing import List, Dict, Any, Optional
from services.execution.models import Run, StepResult
from services.planner.models import ExecutionPlan
from .models import ReplayComparison, ReplayMismatch

class ComparisonEngine:
    def compare(self, source_run: Run, replay_run: Run, source_plan: ExecutionPlan, replay_plan: ExecutionPlan) -> ReplayComparison:
        mismatches = []

        # 1. Plan Match
        plan_match = self._compare_plans(source_plan, replay_plan, mismatches)

        # 2. Structural Match
        step_count_match = len(source_run.step_results) == len(replay_run.step_results)
        if not step_count_match:
            mismatches.append(ReplayMismatch(
                category="artifact",
                step_id=None,
                expected=f"{len(source_run.step_results)} steps",
                actual=f"{len(replay_run.step_results)} steps",
                severity="error"
            ))

        source_steps_ordered = sorted(source_run.step_results.keys(), key=lambda k: source_run.step_results[k].started_at or "")
        replay_steps_ordered = sorted(replay_run.step_results.keys(), key=lambda k: replay_run.step_results[k].started_at or "")
        step_order_match = source_steps_ordered == replay_steps_ordered
        if not step_order_match:
             mismatches.append(ReplayMismatch(
                category="step_order",
                step_id=None,
                expected=source_steps_ordered,
                actual=replay_steps_ordered,
                severity="error"
            ))

        # 3. Outcome Match
        status_match = source_run.status == replay_run.status
        if not status_match:
            mismatches.append(ReplayMismatch(
                category="artifact",
                step_id=None,
                expected=source_run.status,
                actual=replay_run.status,
                severity="error"
            ))

        # 4. Output Match and per-step details
        outputs_match = True
        for step_id in source_run.step_results:
            if step_id not in replay_run.step_results:
                continue

            s_res = source_run.step_results[step_id]
            r_res = replay_run.step_results[step_id]

            if s_res.status != r_res.status:
                mismatches.append(ReplayMismatch(
                    category="step_status",
                    step_id=step_id,
                    expected=s_res.status,
                    actual=r_res.status,
                    severity="error"
                ))
                status_match = False

            if s_res.outputs != r_res.outputs:
                mismatches.append(ReplayMismatch(
                    category="step_output",
                    step_id=step_id,
                    expected=s_res.outputs,
                    actual=r_res.outputs,
                    severity="warning"
                ))
                outputs_match = False

            if s_res.final_attempt_count != r_res.final_attempt_count:
                mismatches.append(ReplayMismatch(
                    category="retry_count",
                    step_id=step_id,
                    expected=s_res.final_attempt_count,
                    actual=r_res.final_attempt_count,
                    severity="warning"
                ))

        # 5. Rollback Match
        rollback_match = (source_run.rollback_status == replay_run.rollback_status and
                          source_run.consistency_outcome == replay_run.consistency_outcome)
        if not rollback_match:
            mismatches.append(ReplayMismatch(
                category="rollback",
                step_id=None,
                expected={"status": source_run.rollback_status, "outcome": source_run.consistency_outcome},
                actual={"status": replay_run.rollback_status, "outcome": replay_run.consistency_outcome},
                severity="error"
            ))

        return ReplayComparison(
            plan_match=plan_match,
            step_order_match=step_order_match,
            step_count_match=step_count_match,
            status_match=status_match,
            outputs_match=outputs_match,
            rollback_match=rollback_match,
            mismatches=mismatches
        )

    def _compare_plans(self, s_plan: ExecutionPlan, r_plan: ExecutionPlan, mismatches: List[ReplayMismatch]) -> bool:
        match = True
        if len(s_plan.steps) != len(r_plan.steps):
            mismatches.append(ReplayMismatch(
                category="plan",
                step_id=None,
                expected=f"{len(s_plan.steps)} plan steps",
                actual=f"{len(r_plan.steps)} plan steps",
                severity="error"
            ))
            match = False

        for sid, s_step in s_plan.steps.items():
            if sid not in r_plan.steps:
                mismatches.append(ReplayMismatch(
                    category="plan",
                    step_id=sid,
                    expected="Present in source plan",
                    actual="Missing in replay plan",
                    severity="error"
                ))
                match = False
                continue

            r_step = r_plan.steps[sid]
            if s_step.step_type != r_step.step_type:
                mismatches.append(ReplayMismatch(
                    category="plan",
                    step_id=sid,
                    expected=s_step.step_type,
                    actual=r_step.step_type,
                    severity="error"
                ))
                match = False

            if s_step.dependencies != r_step.dependencies:
                 mismatches.append(ReplayMismatch(
                    category="plan",
                    step_id=sid,
                    expected=s_step.dependencies,
                    actual=r_step.dependencies,
                    severity="error"
                ))
                 match = False

        return match

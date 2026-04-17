from __future__ import annotations
from typing import List, Dict, Any, Optional
from pathlib import Path
import json

from services.execution.models import Run, StepResult
from services.execution.rollback_models import RollbackPlan, CompensationAction, CompensationType
from services.execution.compensation_handlers import CompensationHandlers
from services.planner.models import ExecutionPlan, Step

class RollbackPlanner:
    def __init__(self, plan: ExecutionPlan):
        self.plan = plan

    def build_rollback_plan(self, run: Run, ordered_step_ids: List[str]) -> RollbackPlan:
        rollback_id = f"rollback_{run.run_id}"
        actions = []

        # Reverse the order of steps that were completed
        completed_step_ids = [sid for sid in ordered_step_ids if run.step_results.get(sid) and run.step_results[sid].status == "completed"]
        reversed_step_ids = reversed(completed_step_ids)

        for step_id in reversed_step_ids:
            step = self.plan.steps[step_id]
            step_result = run.step_results[step_id]

            comp_type = step.contract.compensation_type
            comp_template = step.contract.compensation_template

            if comp_type == "non_reversible":
                continue

            if not comp_template or comp_template == "noop_record_only":
                action = CompensationAction(
                    compensation_id=f"comp_{step_id}",
                    source_step_id=step_id,
                    action_type="noop_record_only",
                    target=step.target
                )
                actions.append(action)
                continue

            action = CompensationAction(
                compensation_id=f"comp_{step_id}",
                source_step_id=step_id,
                action_type=comp_template, # type: ignore
                target=step.target,
                inputs=step_result.rollback_metadata
            )
            actions.append(action)

        return RollbackPlan(
            rollback_id=rollback_id,
            run_id=run.run_id,
            actions=actions
        )

class RollbackEngine:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def execute(self, rollback_plan: RollbackPlan, run: Run, logger: Any):
        print("ROLLBACK START")
        rollback_plan.status = "running"
        run.rollback_status = "running"

        handlers = CompensationHandlers(self.workspace_root, run.run_id)

        all_success = True
        any_failed = False
        any_non_reversible = False

        # Check if there were any non-reversible steps that were completed
        # Actually, RollbackPlanner already handles this by skipping them in actions,
        # but we should note if they existed to set consistency_outcome correctly.
        # But wait, the spec says "completed only for reversible steps, consistency = partially_restored"

        # Let's re-scan completed steps for non-reversible ones
        for step_id, result in run.step_results.items():
            if result.status == "completed":
                # We need access to the plan to know the step type/contract
                # For now let's assume if it's not in rollback actions it might be non-reversible
                pass

        for i, action in enumerate(rollback_plan.actions):
            print(f"[{i+1}/{len(rollback_plan.actions)}] {action.action_type} {action.target or ''} → ", end="", flush=True)
            action.status = "running"
            try:
                handler = handlers.get_handler(action.action_type)
                handler(action)
                action.status = "completed"
                logger.log_compensation_action(run.run_id, action)
                print("completed")
            except Exception as e:
                action.status = "failed"
                action.error_message = str(e)
                if ":" in str(e):
                    action.error_code = str(e).split(":")[0]
                else:
                    action.error_code = "COMPENSATION_FAILED"
                print(f"failed ({action.error_code})")
                all_success = False
                any_failed = True
                rollback_plan.issues.append(f"Action {action.compensation_id} failed: {str(e)}")

        # Determine final status
        if any_failed:
            rollback_plan.status = "failed"
            run.rollback_status = "failed"
        elif all_success:
            rollback_plan.status = "completed"
            run.rollback_status = "completed"
        else:
            # Should not happen with current logic
            rollback_plan.status = "completed_with_warnings"
            run.rollback_status = "completed_with_warnings"

        # Consistency outcome
        # v1 rule:
        # clean: all eligible reversible actions completed successfully AND no non-reversible steps were completed.
        # partially_restored: some succeeded, some failed, OR some non-reversible steps existed.
        # not_restored: rollback failed materially.

        # We need to know if there were non-reversible steps.
        # Let's pass that info from the planner or calculate it here if we had the plan.
        # For simplicity in v1, let's look at the actions.

        # Actually, let's refine this in engine.py where we have all info.

        print(f"ROLLBACK {rollback_plan.status.upper()}")

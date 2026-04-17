from __future__ import annotations
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from services.planner.models import ExecutionPlan, Step
from services.execution.models import Run, StepResult, StepAttempt, HandlerResult
from services.execution.logger import ExecutionLogger
from services.execution.contracts import ContractEvaluator
from services.execution.handlers import StepHandlers
from services.execution.retry_policy import get_retry_policy
from services.execution.retry_classifier import classify_failure
from services.execution.rollback import RollbackPlanner, RollbackEngine

class ExecutionEngine:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.logger = ExecutionLogger(workspace_root)
        self.contracts = ContractEvaluator(workspace_root)

    def execute(self, plan: ExecutionPlan) -> Run:
        print("RUN START")
        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run = Run(run_id=run_id, plan_id=plan.plan_id, status="running")
        self.logger.log_run(run)

        self.handlers = StepHandlers(self.workspace_root, run_id=run_id)

        ordered_steps = self._get_ordered_steps(plan)

        failed = False
        for i, step_id in enumerate(ordered_steps):
            step = plan.steps[step_id]

            if failed:
                self._skip_step(run, step)
                continue

            if not self._dependencies_satisfied(run, step):
                self._fail_step(run, step, "DEPENDENCY_NOT_SATISFIED", "One or more dependencies failed or were skipped")
                failed = True
                continue

            result = self._execute_step_with_retry(run, step, i+1, len(ordered_steps))
            if result.status == "failed":
                failed = True

        run.status = "failed" if failed else "completed"

        if failed:
            self._handle_rollback(plan, run, ordered_steps)

        run.ended_at = datetime.now()
        self.logger.log_run(run)
        print(f"RUN {'FAILED' if failed else 'COMPLETED'}")
        if failed:
            print(f"CONSISTENCY OUTCOME: {run.consistency_outcome}")
        return run

    def _handle_rollback(self, plan: ExecutionPlan, run: Run, ordered_step_ids: List[str]):
        # Rollback Trigger Rules
        has_reversible = any(
            run.step_results.get(sid) and
            run.step_results[sid].status == "completed" and
            plan.steps[sid].contract.compensation_type in ["reversible", "compensatable"]
            for sid in ordered_step_ids
        )

        if not has_reversible:
            run.rollback_status = "not_needed"
            # If failed but nothing to rollback, check for non-reversible steps that were completed
            has_non_reversible = any(
                run.step_results.get(sid) and
                run.step_results[sid].status == "completed" and
                plan.steps[sid].contract.compensation_type == "non_reversible"
                for sid in ordered_step_ids
            )
            run.consistency_outcome = "not_restored" if has_non_reversible else "clean"
            return

        planner = RollbackPlanner(plan)
        rollback_plan = planner.build_rollback_plan(run, ordered_step_ids)
        self.logger.log_rollback_plan(run.run_id, rollback_plan)

        engine = RollbackEngine(self.workspace_root)
        engine.execute(rollback_plan, run, self.logger)
        self.logger.log_rollback_plan(run.run_id, rollback_plan)

        # Update consistency outcome
        all_reversible_undone = True
        any_failed = (rollback_plan.status == "failed")

        # Check if all completed steps that were reversible have a corresponding successful action
        completed_reversible_step_ids = [
            sid for sid in ordered_step_ids
            if run.step_results.get(sid) and
            run.step_results[sid].status == "completed" and
            plan.steps[sid].contract.compensation_type in ["reversible", "compensatable"]
        ]

        for sid in completed_reversible_step_ids:
            action = next((a for a in rollback_plan.actions if a.source_step_id == sid), None)
            if not action or action.status != "completed":
                all_reversible_undone = False
                break

        has_non_reversible = any(
            run.step_results.get(sid) and
            run.step_results[sid].status == "completed" and
            plan.steps[sid].contract.compensation_type == "non_reversible"
            for sid in ordered_step_ids
        )

        if any_failed:
            run.consistency_outcome = "not_restored"
        elif not all_reversible_undone or has_non_reversible:
            run.consistency_outcome = "partially_restored"
        else:
            run.consistency_outcome = "clean"

    def _get_ordered_steps(self, plan: ExecutionPlan) -> List[str]:
        # Simple topological sort or use dependency order
        visited = set()
        ordered = []

        def visit(step_id):
            if step_id in visited:
                return
            step = plan.steps[step_id]
            for dep_id in step.dependencies:
                visit(dep_id)
            visited.add(step_id)
            ordered.append(step_id)

        for step_id in plan.steps:
            visit(step_id)

        return ordered

    def _dependencies_satisfied(self, run: Run, step: Step) -> bool:
        for dep_id in step.dependencies:
            dep_result = run.step_results.get(dep_id)
            if not dep_result or dep_result.status != "completed":
                return False
        return True

    def _execute_step_with_retry(self, run: Run, step: Step, step_index: int, total_steps: int) -> StepResult:
        policy = get_retry_policy(step.step_type)
        run.current_step_id = step.step_id
        result = StepResult(step_id=step.step_id, status="running", started_at=datetime.now(), inputs=step.inputs)
        run.step_results[step.step_id] = result
        self.logger.log_step(run.run_id, result)

        attempt_index = 1
        while attempt_index <= policy.max_attempts:
            attempt = StepAttempt(attempt_index=attempt_index, started_at=datetime.now())
            result.attempts.append(attempt)
            result.final_attempt_count = attempt_index
            self.logger.log_step(run.run_id, result)

            # 1. Preconditions
            if not self.contracts.evaluate_preconditions(step):
                attempt.status = "failed"
                attempt.error_code = "PRECONDITION_FAILED"
                attempt.error_message = "Preconditions not met"
                attempt.ended_at = datetime.now()
                # Precondition failures are terminal by default in Spec
                self._finalize_step_failure(run, result, attempt.error_code, attempt.error_message)
                print(f"[{step_index}/{total_steps}] {step.step_type} → {result.status} ({result.error_code})")
                return result

            attempt.preconditions_passed = True

            # 2. Handler
            is_transient = None
            try:
                handler = self.handlers.get_handler(step.step_type)
                handler_result = handler(step)

                if isinstance(handler_result, HandlerResult):
                    attempt.outputs = handler_result.outputs
                    attempt.rollback_metadata = handler_result.rollback_metadata
                    if handler_result.success:
                        attempt.status = "completed"
                    else:
                        attempt.status = "failed"
                        attempt.error_code = handler_result.error_code or "EXECUTION_ERROR"
                        attempt.error_message = handler_result.error_message
                        is_transient = handler_result.is_transient
                else:
                    # Assume dict success
                    attempt.outputs = handler_result
                    attempt.status = "completed"
            except Exception as e:
                attempt.status = "failed"
                error_msg = str(e)
                if ":" in error_msg:
                    parts = error_msg.split(":", 1)
                    attempt.error_code = parts[0].strip()
                    attempt.error_message = parts[1].strip()
                else:
                    attempt.error_code = "EXECUTION_ERROR"
                    attempt.error_message = error_msg

            # 3. Postconditions
            if attempt.status == "completed":
                if not self.contracts.evaluate_postconditions(step, attempt.outputs):
                    attempt.status = "failed"
                    attempt.error_code = "POSTCONDITION_FAILED"
                    attempt.error_message = "Postconditions not met"
                else:
                    attempt.postconditions_passed = True

            attempt.ended_at = datetime.now()

            if attempt.status == "completed":
                result.status = "completed"
                result.outputs = attempt.outputs
                result.rollback_metadata = attempt.rollback_metadata
                result.preconditions_passed = attempt.preconditions_passed
                result.postconditions_passed = attempt.postconditions_passed
                result.ended_at = datetime.now()
                if attempt_index > 1:
                    result.recovered_via_retry = True
                    run.recovered_steps += 1

                self.logger.log_step(run.run_id, result)
                print(f"[{step_index}/{total_steps}] {step.step_type} → {result.status}" + (f" on attempt {attempt_index}" if attempt_index > 1 else ""))
                return result

            # Failure handling
            classification = classify_failure(attempt.error_code, step.step_type, is_transient=is_transient)
            if classification == "terminal" or attempt_index == policy.max_attempts:
                self._finalize_step_failure(run, result, attempt.error_code, attempt.error_message)
                if attempt_index == policy.max_attempts and classification == "retryable":
                    result.retry_exhausted = True
                    run.retry_exhausted_steps += 1

                print(f"[{step_index}/{total_steps}] {step.step_type} → {result.status} ({result.error_code})" + (f" attempt {attempt_index}/{policy.max_attempts}" if policy.max_attempts > 1 else ""))
                return result

            # Retry logic
            print(f"[{step_index}/{total_steps}] {step.step_type} → failed attempt {attempt_index}/{policy.max_attempts} ({attempt.error_code})")

            delay = self._calculate_delay(policy, attempt_index)
            print(f"[{step_index}/{total_steps}] {step.step_type} → retrying in {delay}ms")
            time.sleep(delay / 1000.0)
            run.total_retries += 1

            if policy.requires_recheck:
                if not self._recheck_step(step):
                    print(f"[{step_index}/{total_steps}] {step.step_type} → recheck failed, aborting retry")
                    self._finalize_step_failure(run, result, attempt.error_code, attempt.error_message)
                    return result

            attempt_index += 1

        return result

    def _calculate_delay(self, policy, attempt_index: int) -> int:
        if policy.backoff_mode == "fixed":
            return policy.delay_ms
        elif policy.backoff_mode == "linear":
            return policy.delay_ms * attempt_index
        return 0

    def _recheck_step(self, step: Step) -> bool:
        # File-related step
        if step.step_type in ["read_file", "write_file", "modify_file", "create_file", "verify_file_exists", "validate_output"]:
            if step.target:
                path = self.workspace_root / step.target
                # For read/modify/verify/validate, it must exist
                if step.step_type in ["read_file", "modify_file", "verify_file_exists", "validate_output"]:
                    return path.exists()
                # For create_file, parent must exist
                if step.step_type == "create_file":
                    return path.parent.exists()

        # Command-related step
        if step.step_type == "run_command":
            # verify working directory still valid
            return self.workspace_root.exists()

        return True

    def _finalize_step_failure(self, run: Run, result: StepResult, error_code: str, error_message: str):
        result.status = "failed"
        result.error_code = error_code
        result.error_message = error_message
        result.ended_at = datetime.now()
        self.logger.log_step(run.run_id, result)

    def _fail_step(self, run: Run, step: Step, error_code: str, error_message: str) -> StepResult:
        result = run.step_results.get(step.step_id)
        if not result:
            result = StepResult(step_id=step.step_id, inputs=step.inputs)
            run.step_results[step.step_id] = result

        result.status = "failed"
        result.error_code = error_code
        result.error_message = error_message
        result.ended_at = datetime.now()
        self.logger.log_step(run.run_id, result)
        return result

    def _skip_step(self, run: Run, step: Step):
        result = StepResult(step_id=step.step_id, status="skipped", inputs=step.inputs)
        run.step_results[step.step_id] = result
        self.logger.log_step(run.run_id, result)

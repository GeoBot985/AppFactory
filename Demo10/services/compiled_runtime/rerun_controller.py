from __future__ import annotations
import time
from typing import Dict, Any, Optional
from services.compiler.models import CompiledPlan
from services.task_executor_service import TaskExecutorService
from .run_models import CompiledPlanRun, CompiledTaskState, CompiledRunStatus, CompiledTaskStatus
from .run_context import SharedRunContext
from .task_dispatcher import CompiledTaskDispatcher
from .rerun_models import ReRunPlan

class ReRunController:
    def __init__(self, executor: TaskExecutorService):
        self.executor = executor
        self.dispatcher = CompiledTaskDispatcher(executor)

    def execute_rerun(self, plan: CompiledPlan, base_run: CompiledPlanRun, rerun_plan: ReRunPlan) -> CompiledPlanRun:
        # 1. Initialize New Run State based on Base Run
        new_run = CompiledPlanRun(
            compiled_plan_id=plan.plan_id,
            run_id=rerun_plan.rerun_id,
            tasks_total=len(plan.tasks),
            fail_fast=base_run.fail_fast,
            base_run_id=base_run.run_id
        )

        # Lineage record
        new_run.rerun_lineage = {
            "base_run_id": rerun_plan.base_run_id,
            "rerun_id": rerun_plan.rerun_id,
            "rerun_reason": rerun_plan.reason,
            "requested_start_task_id": rerun_plan.start_task_id,
            "resolved_rerun_range": rerun_plan.rerun_tasks,
            "artifact_reuse_summary": rerun_plan.artifact_reuse_summary,
            "invalidated_task_ids": rerun_plan.invalidated_tasks
        }

        # 2. Setup Context with Reused Artifacts
        context = SharedRunContext()

        # Initialize all task states
        for task in plan.tasks:
            base_state = base_run.task_states.get(task.id)
            new_state = CompiledTaskState(
                task_id=task.id,
                task_type=task.type.value,
                depends_on=task.depends_on
            )

            if task.id in rerun_plan.reused_tasks:
                if base_state:
                    new_state.status = CompiledTaskStatus.REUSED
                    new_state.artifacts = base_state.artifacts.copy()
                    new_state.result_summary = f"Reused from {base_run.run_id}"
                    new_state.bundle = base_state.bundle
                    # Re-populate shared context from reused artifacts if they match known keys
                    self._repopulate_context(context, task.id, new_state.artifacts)
                new_run.tasks_succeeded += 1
            elif task.id == rerun_plan.start_task_id:
                new_state.status = CompiledTaskStatus.RERUN_PENDING
            elif task.id in rerun_plan.invalidated_tasks:
                new_state.status = CompiledTaskStatus.INVALIDATED

            new_run.task_states[task.id] = new_state

        # 3. Start Execution of Rerun Range
        new_run.overall_status = CompiledRunStatus.RUNNING

        for task_id in plan.execution_graph:
            if task_id in rerun_plan.reused_tasks:
                continue

            if task_id not in rerun_plan.rerun_tasks:
                # This should not happen if invalidation logic is correct and graph is followed
                continue

            task = next((t for t in plan.tasks if t.id == task_id), None)
            if not task: continue

            new_run.current_task_id = task_id
            task_state = new_run.task_states[task_id]
            task_state.status = CompiledTaskStatus.RUNNING

            # Dispatch task
            result = self.dispatcher.dispatch(task, task_state, context)

            # Tag status for rerun
            if result.success:
                task_state.status = CompiledTaskStatus.RERUN_SUCCEEDED
                new_run.tasks_succeeded += 1
            else:
                task_state.status = CompiledTaskStatus.RERUN_FAILED
                new_run.tasks_failed += 1
                if new_run.fail_fast:
                    new_run.overall_status = CompiledRunStatus.FAILED
                    self._mark_remaining_blocked(plan, new_run)
                    break

        if new_run.overall_status == CompiledRunStatus.RUNNING:
            if new_run.tasks_failed > 0:
                 new_run.overall_status = CompiledRunStatus.FAILED
            else:
                 new_run.overall_status = CompiledRunStatus.SUCCESS

        new_run.completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        return new_run

    def _repopulate_context(self, context: SharedRunContext, task_id: str, artifacts: Dict[str, Any]):
        # This is a bit heuristic, mapping artifacts back to context fields
        if "context_package" in artifacts:
            context.selected_context = artifacts["context_package"]
        if "scope_contract" in artifacts:
            context.scope_contract = artifacts["scope_contract"]
        # etc. for other known keys in SharedRunContext
        # Ideally we'd have a more formal way to serialize/deserialize the whole context
        if "mutation_batch" in artifacts:
            batch = artifacts["mutation_batch"]
            if hasattr(batch, 'results'):
                context.candidate_file_ops.extend(batch.results)

    def _mark_remaining_blocked(self, plan: CompiledPlan, run: CompiledPlanRun):
        started_marking = False
        for tid in plan.execution_graph:
            if tid == run.current_task_id:
                started_marking = True
                continue
            if started_marking:
                tstate = run.task_states.get(tid)
                if tstate and tstate.status in [CompiledTaskStatus.PENDING, CompiledTaskStatus.INVALIDATED, CompiledTaskStatus.RERUN_PENDING]:
                    tstate.status = CompiledTaskStatus.BLOCKED
                    tstate.result_summary = "Aborted due to rerun fail-fast"
                    run.tasks_skipped += 1

from __future__ import annotations
import time
from typing import List, Dict, Any, Optional
from services.compiler.models import CompiledPlan
from services.task_service import Task, TaskStatus
from services.task_executor_service import TaskExecutorService
from .run_models import CompiledPlanRun, CompiledTaskState, CompiledRunStatus, CompiledTaskStatus
from .run_context import SharedRunContext
from .task_dispatcher import CompiledTaskDispatcher
from .task_adapters import ADAPTER_MAP
from .rerun_models import ReRunRequest, ReRunPlan
from .rerun_planner import plan_rerun
from .rerun_controller import ReRunController
from metrics.metrics_service import MetricsService

class CompiledPlanRunController:
    def __init__(self, executor: TaskExecutorService):
        self.executor = executor
        self.metrics = getattr(executor, "metrics", None) or MetricsService(getattr(executor, "run_folder", None))
        self.dispatcher = CompiledTaskDispatcher(executor, self.metrics)
        self.rerun_controller = ReRunController(executor)

    def execute_compiled_plan(self, plan: CompiledPlan, run_id: str, context: Optional[SharedRunContext] = None) -> CompiledPlanRun:
        self.metrics.start_run(run_id)
        # 1. Initialize Run State
        run = CompiledPlanRun(
            compiled_plan_id=plan.plan_id,
            run_id=run_id,
            tasks_total=len(plan.tasks),
            fail_fast=plan.policies.get("fail_fast", True)
        )

        # Initialize task states
        for task in plan.tasks:
            run.task_states[task.id] = CompiledTaskState(
                task_id=task.id,
                task_type=task.type.value,
                depends_on=task.depends_on
            )

        # 2. Validate Adapter Coverage
        self.metrics.start_high_level_stage("compile") # Or intake stage?
        valid = self._validate_adapter_coverage(plan, run)
        self.metrics.end_high_level_stage("compile", success=valid)
        if not valid:
            run.overall_status = CompiledRunStatus.FAILED
            run.completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
            self.metrics.end_run()
            return run

        # 3. Start Execution
        self.metrics.start_high_level_stage("execution")
        run.overall_status = CompiledRunStatus.RUNNING
        if context is None:
            context = SharedRunContext()

        # Execute in graph order
        for task_id in plan.execution_graph:
            task = next((t for t in plan.tasks if t.id == task_id), None)
            if not task:
                continue

            run.current_task_id = task_id
            task_state = run.task_states[task_id]

            # Check dependencies
            if not self._check_dependencies(task, run):
                task_state.status = CompiledTaskStatus.BLOCKED
                task_state.result_summary = "Dependency failed"
                run.tasks_skipped += 1
                if run.fail_fast:
                    run.overall_status = CompiledRunStatus.FAILED
                    break
                continue

            # Dispatch task
            result = self.dispatcher.dispatch(task, task_state, context)

            if result.success:
                run.tasks_succeeded += 1
            else:
                run.tasks_failed += 1
                if run.fail_fast:
                    run.overall_status = CompiledRunStatus.FAILED
                    self._mark_remaining_blocked(plan, run)
                    break

        if run.overall_status == CompiledRunStatus.RUNNING:
            if run.tasks_failed > 0:
                 run.overall_status = CompiledRunStatus.FAILED
            else:
                 run.overall_status = CompiledRunStatus.SUCCESS

        self.metrics.end_high_level_stage("execution", success=(run.overall_status == CompiledRunStatus.SUCCESS))
        run.completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.metrics.end_run()
        return run

    def _validate_adapter_coverage(self, plan: CompiledPlan, run: CompiledPlanRun) -> bool:
        missing_adapters = []
        for task in plan.tasks:
            if task.type not in ADAPTER_MAP:
                missing_adapters.append(str(task.type))

        if missing_adapters:
            msg = f"Unsupported compiled task types: {', '.join(set(missing_adapters))}"
            run.overall_status = CompiledRunStatus.FAILED
            # In some environments overall_status might be an Enum, let's be safe
            # and maybe add a message field to CompiledPlanRun if we want to store this.
            # For now, let's just ensure task states reflect it.

            for task in plan.tasks:
                if str(task.type) in missing_adapters:
                    run.task_states[task.id].status = CompiledTaskStatus.FAILED
                    run.task_states[task.id].result_summary = f"Unsupported task type: {task.type}"
            return False
        return True

    def _check_dependencies(self, task: Task, run: CompiledPlanRun) -> bool:
        for dep_id in task.depends_on:
            dep_state = run.task_states.get(dep_id)
            if not dep_state or dep_state.status != CompiledTaskStatus.SUCCEEDED:
                return False
        return True

    def _mark_remaining_blocked(self, plan: CompiledPlan, run: CompiledPlanRun):
        started_marking = False
        for tid in plan.execution_graph:
            if tid == run.current_task_id:
                started_marking = True
                continue
            if started_marking:
                tstate = run.task_states.get(tid)
                if tstate and tstate.status == CompiledTaskStatus.PENDING:
                    tstate.status = CompiledTaskStatus.BLOCKED
                    tstate.result_summary = "Aborted due to fail-fast"
                    run.tasks_skipped += 1

    def request_rerun(self, plan: CompiledPlan, base_run: CompiledPlanRun, request: ReRunRequest) -> CompiledPlanRun:
        self.metrics.start_run(f"{base_run.run_id}_rerun_{int(time.time())}")
        self.metrics.start_high_level_stage("rerun")
        try:
            rerun_plan = plan_rerun(plan, base_run, request)
            return self.rerun_controller.execute_rerun(plan, base_run, rerun_plan)
        finally:
            self.metrics.end_high_level_stage("rerun")
            self.metrics.end_run()

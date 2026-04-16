from __future__ import annotations
import uuid
from pathlib import Path
from typing import Optional
from services.compiler.models import CompiledPlan
from services.task_executor_service import TaskExecutorService
from services.compiled_runtime.run_controller import CompiledPlanRunController
from .impact_model import ImpactPreview, ImpactSummary
from .diff_builder import DiffBuilder
from .risk_analyzer import RiskAnalyzer

class PlanSimulator:
    def __init__(self, executor: TaskExecutorService):
        self.executor = executor
        self.diff_builder = DiffBuilder(executor.file_ops.project_root)
        self.risk_analyzer = RiskAnalyzer()

    def simulate(self, plan: CompiledPlan) -> ImpactPreview:
        # 1. Setup simulation environment
        # We need to run the CompiledPlanRunController in a way that captures candidate mutations
        # but does NOT apply them.
        # The existing TaskExecutorService.mutation_mode = "dry-run" helps.

        controller = CompiledPlanRunController(self.executor)

        # We need a way to run the plan and get the SharedRunContext back.
        # Currently execute_compiled_plan doesn't return the context.
        # I might need to modify CompiledPlanRunController or subclass it.

        # For now, let's assume we can get the context or the resulting mutations.
        # Actually, let's look at how execute_compiled_plan works.
        # It calls dispatcher.dispatch which updates SharedRunContext.

        from services.compiled_runtime.run_context import SharedRunContext
        from services.compiled_runtime.run_models import CompiledTaskState

        run_id = f"sim_{uuid.uuid4().hex[:8]}"
        context = SharedRunContext()

        # Prepare task states (similar to execute_compiled_plan)
        task_states = {}
        for task in plan.tasks:
            task_states[task.id] = CompiledTaskState(
                task_id=task.id,
                task_type=task.type.value,
                depends_on=task.depends_on
            )

        # Simulation Loop (No Disk Writes)
        # We MUST ensure executor is in dry-run mode
        original_mode = self.executor.mutation_mode
        self.executor.mutation_mode = "dry-run"

        try:
            for task_id in plan.execution_graph:
                task = next((t for t in plan.tasks if t.id == task_id), None)
                if not task: continue

                # Check dependencies - in simulation we might want to continue even if some fail?
                # But for a realistic preview, we follow the graph.
                if not self._check_dependencies(task, task_states):
                    task_states[task_id].status = "blocked"
                    continue

                # Dispatch
                # We don't want to run ACTUAL commands if they are dangerous,
                # but Spec 031 says "simulate execution ... up to mutation stage".
                # Usually this means running generation, but maybe NOT running actual tests/commands
                # unless they are in a temp workspace.

                # To be safe, we only dispatch READ and GENERATE tasks.
                if "GENERATE" in task.type.value or "READ" in task.type.value or "PATCH" in task.type.value or "CREATE" in task.type.value:
                    controller.dispatcher.dispatch(task, task_states[task_id], context)
        finally:
            self.executor.mutation_mode = original_mode

        # 2. Build Impact Preview from context.candidate_file_ops
        preview = ImpactPreview(
            preview_id=run_id,
            compiled_plan_id=plan.plan_id,
            workspace_hash=self._get_workspace_hash()
        )

        summary = ImpactSummary()
        for op in context.candidate_file_ops:
            file_diff = self.diff_builder.build_file_diff(op.path, op.op_type, getattr(op, "content", None))
            preview.file_diffs.append(file_diff)

            if op.op_type == "create_file": summary.files_created += 1
            elif op.op_type == "delete_file": summary.files_deleted += 1
            else: summary.files_modified += 1

            summary.estimated_loc_change += abs(file_diff.line_count_after - file_diff.line_count_before)

        summary.total_files = len(preview.file_diffs)
        preview.summary = summary

        # 3. Analyze Risk
        self.risk_analyzer.analyze(preview)

        return preview

    def _check_dependencies(self, task, task_states) -> bool:
        from services.compiled_runtime.run_models import CompiledTaskStatus
        for dep_id in task.depends_on:
            dep_state = task_states.get(dep_id)
            if not dep_state or dep_state.status != CompiledTaskStatus.SUCCEEDED:
                return False
        return True

    def _get_workspace_hash(self) -> str:
        # Minimal implementation
        import hashlib
        return hashlib.md5(str(self.executor.file_ops.project_root).encode()).hexdigest()

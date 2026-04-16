from __future__ import annotations
import uuid
from typing import Optional, List, Set, Dict, Any
from services.compiler.models import CompiledPlan
from .run_models import CompiledPlanRun, CompiledTaskStatus
from .rerun_models import ReRunRequest, ReRunPlan, ReRunType
from .invalidation import compute_invalidated_downstream_steps

def plan_rerun(
    plan: CompiledPlan,
    base_run: CompiledPlanRun,
    request: ReRunRequest
) -> ReRunPlan:
    # 1. Validate entry conditions
    if plan.is_stale:
        raise ValueError("Cannot rerun against a stale compiled plan")

    if request.base_run_id != base_run.run_id:
        raise ValueError(f"Run ID mismatch: {request.base_run_id} vs {base_run.run_id}")

    # Determine start task
    start_task_id = request.start_task_id
    if request.rerun_type == ReRunType.RERUN_FAILED_TASK:
        # Find first failed task
        for tid in plan.execution_graph:
            tstate = base_run.task_states.get(tid)
            if tstate and tstate.status == CompiledTaskStatus.FAILED:
                start_task_id = tid
                break
        if not start_task_id:
            raise ValueError("No failed task found to rerun")
    elif request.rerun_type == ReRunType.RERUN_VALIDATION_SUFFIX:
        # Find first validation/test task after the last successful generation
        # For now, let's just use the first validation-like task that failed or is pending
        for tid in plan.execution_graph:
            tstate = base_run.task_states.get(tid)
            task = next(t for t in plan.tasks if t.id == tid)
            if "validation" in task.type.value.lower() or "test" in task.type.value.lower():
                start_task_id = tid
                break
        if not start_task_id:
            raise ValueError("No validation/test task found for rerun_validation_suffix")

    if not start_task_id or start_task_id not in base_run.task_states:
        raise ValueError(f"Invalid start task ID: {start_task_id}")

    # 2. Compute ranges
    invalidated_ids = compute_invalidated_downstream_steps(plan, start_task_id)

    rerun_tasks = [start_task_id] + sorted(list(invalidated_ids), key=lambda x: plan.execution_graph.index(x))

    reused_tasks = []
    for tid in plan.execution_graph:
        if tid == start_task_id:
            break
        reused_tasks.append(tid)

    # 3. Artifact reuse summary
    artifact_reuse_summary = {}
    for tid in reused_tasks:
        tstate = base_run.task_states.get(tid)
        if tstate:
            artifact_reuse_summary[tid] = list(tstate.artifacts.keys())

    return ReRunPlan(
        base_run_id=base_run.run_id,
        rerun_id=f"rerun_{uuid.uuid4().hex[:8]}",
        start_task_id=start_task_id,
        reused_tasks=reused_tasks,
        rerun_tasks=rerun_tasks,
        invalidated_tasks=list(invalidated_ids),
        artifact_reuse_summary=artifact_reuse_summary,
        reason=request.reason
    )

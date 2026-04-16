from __future__ import annotations
from typing import List, Set, Dict
from services.compiler.models import CompiledPlan
from .run_models import CompiledTaskStatus

def compute_invalidated_downstream_steps(
    plan: CompiledPlan,
    start_task_id: str
) -> Set[str]:
    """
    Finds all tasks that depend on start_task_id directly or indirectly.
    """
    invalidated = {start_task_id}

    # Simple BFS/DFS to find all descendants in the dependency graph
    changed = True
    while changed:
        changed = False
        for task in plan.tasks:
            if task.id in invalidated:
                continue

            # If any dependency is invalidated, this task is invalidated
            for dep_id in task.depends_on:
                if dep_id in invalidated:
                    invalidated.add(task.id)
                    changed = True
                    break

    # We don't want to include the start_task_id itself in the 'invalidated' list
    # if we are using it to mark downstream. But the spec says:
    # "If step S is rerun, all steps depending on S or its produced artifacts must be marked invalidated."
    # So the return set should probably be everything AFTER S.

    return invalidated - {start_task_id}

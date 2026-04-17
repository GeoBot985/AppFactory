from .plan_builder import PlanBuilder
from .models import Step, ExecutionPlan, StepContract, PlanIssue

from typing import Any, Dict, List

class Planner:
    def build_task_graph(self, spec_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        tasks = spec_data.get("tasks", [])
        task_map = {t["id"]: t for t in tasks}

        adj = {t["id"]: [] for t in tasks}
        in_degree = {t["id"]: 0 for t in tasks}

        for t in tasks:
            for dep in t.get("depends_on", []):
                adj[dep].append(t["id"])
                in_degree[t["id"]] += 1

        queue = [t["id"] for t in tasks if in_degree[t["id"]] == 0]
        execution_order = []
        while queue:
            queue.sort(key=lambda tid: self._get_original_index(tasks, tid))
            u = queue.pop(0)
            execution_order.append(task_map[u])
            for v in adj[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

        if len(execution_order) != len(tasks):
            raise ValueError("Dependency cycle detected in spec tasks")
        return execution_order

    def _get_original_index(self, tasks: List[Dict[str, Any]], task_id: str) -> int:
        for i, t in enumerate(tasks):
            if t["id"] == task_id:
                return i
        return -1

from __future__ import annotations
from typing import Any, Dict, List, Set, Optional

class Planner:
    def build_task_graph(self, spec_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        tasks = spec_data.get("tasks", [])
        task_map = {t["id"]: t for t in tasks}

        # Build adjacency list
        adj = {t["id"]: [] for t in tasks}
        in_degree = {t["id"]: 0 for t in tasks}

        for t in tasks:
            for dep in t.get("depends_on", []):
                adj[dep].append(t["id"])
                in_degree[t["id"]] += 1

        # Topological Sort (Kahn's algorithm)
        # To ensure determinism when multiple tasks are ready, we sort them by their original order or ID
        queue = [t["id"] for t in tasks if in_degree[t["id"]] == 0]
        # Note: 'tasks' order is already preserved from YAML

        execution_order = []
        while queue:
            # Sort queue to maintain determinism if multiple tasks have 0 in-degree
            # We want to prefer the order they appeared in the spec if possible
            # But Kahn's usually just takes whatever.
            # Let's sort by their original index in the tasks list.
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

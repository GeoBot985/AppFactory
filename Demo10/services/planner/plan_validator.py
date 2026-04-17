from __future__ import annotations
from typing import List, Dict, Any, Set
from services.planner.models import Step, ExecutionPlan, PlanIssue

class PlanValidator:
    def validate(self, plan: ExecutionPlan) -> List[PlanIssue]:
        issues = []

        # 1. Cycle detection
        if self._has_cycles(plan.steps):
            issues.append(PlanIssue(
                code="CYCLIC_DEPENDENCY",
                message="The execution plan contains cyclic dependencies.",
                severity="error"
            ))

        # 2. Conflicting writes
        # Multiple write/modify/create steps for same target without ordering
        # Actually DependencyResolver should have ordered them, but we verify here.
        # If there are two steps for same target, one must depend on other (directly or indirectly)
        # But wait, we only care if they are concurrent.
        # In a DAG, two nodes are concurrent if neither depends on other.
        if self._has_unordered_writes(plan.steps):
             issues.append(PlanIssue(
                code="UNORDERED_WRITES",
                message="Multiple operations target same file without explicit ordering.",
                severity="error"
            ))

        # 3. Missing prerequisite steps
        # E.g. modify without read? (Templates handle this, but still)

        return issues

    def _has_cycles(self, steps: Dict[str, Step]) -> bool:
        visited = set()
        stack = set()

        def visit(sid):
            if sid in stack:
                return True
            if sid in visited:
                return False

            stack.add(sid)
            for dep in steps[sid].dependencies:
                if dep in steps:
                    if visit(dep):
                        return True
            stack.remove(sid)
            visited.add(sid)
            return False

        for sid in steps:
            if visit(sid):
                return True
        return False

    def _has_unordered_writes(self, steps: Dict[str, Step]) -> bool:
        write_steps_by_target: Dict[str, List[str]] = {}
        mutating_types = {"write_file", "modify_file", "create_file", "apply_modification"}

        for sid, step in steps.items():
            if step.step_type in mutating_types and step.target:
                if step.target not in write_steps_by_target:
                    write_steps_by_target[step.target] = []
                write_steps_by_target[step.target].append(sid)

        for target, sids in write_steps_by_target.items():
            if len(sids) < 2:
                continue

            # For each pair, check if there's a path between them
            for i in range(len(sids)):
                for j in range(i + 1, len(sids)):
                    if not self._has_path(steps, sids[i], sids[j]) and not self._has_path(steps, sids[j], sids[i]):
                        return True
        return False

    def _has_path(self, steps: Dict[str, Step], start_id: str, end_id: str) -> bool:
        # Simple BFS/DFS to find if end_id is reachable from start_id?
        # Wait, dependencies are 'depends on', so if B depends on A, path is A -> B.
        # But our Step.dependencies stores [A] in B.
        # So we want to know if start_id is in transitive dependencies of end_id.

        queue = [end_id]
        visited = {end_id}
        while queue:
            curr = queue.pop(0)
            if curr == start_id:
                return True
            for dep in steps[curr].dependencies:
                if dep not in visited and dep in steps:
                    visited.add(dep)
                    queue.append(dep)
        return False

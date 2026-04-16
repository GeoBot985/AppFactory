from __future__ import annotations
from typing import List, Dict, Any, Set, Tuple
from .models import CompileDiagnostic, DiagnosticSeverity

class DependencyGraphNormalizer:
    def normalize(self, tasks: List[Any]) -> Tuple[List[str], List[CompileDiagnostic]]:
        """Returns a topologically sorted list of task IDs and any diagnostics (cycles)."""
        adj = {t.id: t.depends_on for t in tasks}
        visited = set()
        stack = []
        path = set()
        diagnostics = []

        def visit(node_id):
            if node_id in path:
                diagnostics.append(CompileDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="dependency_cycle",
                    message=f"Dependency cycle detected involving {node_id}.",
                    task_id=node_id
                ))
                return
            if node_id in visited:
                return

            path.add(node_id)
            for dep in adj.get(node_id, []):
                visit(dep)
            path.remove(node_id)
            visited.add(node_id)
            stack.append(node_id)

        for t in tasks:
            if t.id not in visited:
                visit(t.id)

        return stack, diagnostics

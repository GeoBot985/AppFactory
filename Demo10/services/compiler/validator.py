from __future__ import annotations
from typing import List, Dict, Any, Tuple
from services.draft_spec.models import DraftSpec, DraftTask, UncertaintySeverity
from .models import CompileDiagnostic, DiagnosticSeverity

class CompilerValidator:
    def validate(self, draft: DraftSpec) -> List[CompileDiagnostic]:
        diagnostics = []

        # Check draft version
        if draft.draft_spec_version != 1:
            diagnostics.append(CompileDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="unsupported_version",
                message=f"Draft spec version {draft.draft_spec_version} is not supported.",
                field_path="draft_spec_version"
            ))

        # Check required fields
        if not draft.title:
            diagnostics.append(CompileDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="missing_title",
                message="Draft title is required.",
                field_path="title"
            ))

        # Check tasks
        task_ids = set()
        for i, task in enumerate(draft.tasks):
            t_prefix = f"tasks[{i}]"
            if not task.id:
                diagnostics.append(CompileDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="missing_task_id",
                    message="Task is missing an ID.",
                    field_path=f"{t_prefix}.id"
                ))
            elif task.id in task_ids:
                diagnostics.append(CompileDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="duplicate_task_id",
                    message=f"Duplicate task ID: {task.id}",
                    field_path=f"{t_prefix}.id",
                    task_id=task.id
                ))
            else:
                task_ids.add(task.id)

            valid_types = ["RUN", "CREATE", "MODIFY", "DELETE", "generate_file"]
            if task.type not in valid_types:
                diagnostics.append(CompileDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="unknown_task_type",
                    message=f"Task {task.id} has an unknown type: {task.type}",
                    field_path=f"{t_prefix}.type",
                    task_id=task.id
                ))

        # Check dependencies
        for i, task in enumerate(draft.tasks):
            for dep in task.depends_on:
                if dep not in task_ids:
                    diagnostics.append(CompileDiagnostic(
                        severity=DiagnosticSeverity.ERROR,
                        code="invalid_dependency",
                        message=f"Task {task.id} depends on non-existent task {dep}.",
                        field_path=f"tasks[{i}].depends_on",
                        task_id=task.id
                    ))

        # Check blocking uncertainties
        for u in draft.uncertainties:
            if u.severity == UncertaintySeverity.BLOCKING:
                diagnostics.append(CompileDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="blocking_uncertainty",
                    message=f"Blocking uncertainty: {u.message}",
                    field_path=u.field_path
                ))

        return diagnostics

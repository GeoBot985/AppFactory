from __future__ import annotations
from typing import List, Dict, Any
from .models import DraftSpec

class DraftSpecValidator:
    def validate_draft_spec_basic(self, draft: DraftSpec) -> List[Dict[str, str]]:
        errors = []
        if not draft.title:
            errors.append({"field": "title", "error": "Missing required field: title"})
        if not draft.tasks:
            errors.append({"field": "tasks", "error": "Draft spec must have at least one task"})

        task_ids = set()
        for i, task in enumerate(draft.tasks):
            if not task.id:
                errors.append({"field": f"tasks[{i}].id", "error": "Task missing ID"})
            elif task.id in task_ids:
                errors.append({"field": f"tasks[{i}].id", "error": f"Duplicate task ID: {task.id}"})
            else:
                task_ids.add(task.id)

            if task.type == "unknown":
                 errors.append({"field": f"tasks[{i}].type", "error": f"Task {task.id} has unknown type"})

        return errors

    def summarize_draft_spec_status(self, draft: DraftSpec) -> Dict[str, Any]:
        errors = self.validate_draft_spec_basic(draft)
        blocking_uncertainties = [u for u in draft.uncertainties if u.severity.value == "blocking"]

        status = "translated"
        if errors:
            status = "invalid"
        elif blocking_uncertainties:
            status = "has_blocking_uncertainties"

        return {
            "status": status,
            "error_count": len(errors),
            "uncertainty_count": len(draft.uncertainties),
            "blocking_uncertainty_count": len(blocking_uncertainties),
            "task_count": len(draft.tasks)
        }

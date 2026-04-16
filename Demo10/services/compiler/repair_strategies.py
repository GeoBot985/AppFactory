from __future__ import annotations
import uuid
import json
from typing import List, Dict, Any, Tuple
from services.draft_spec.models import DraftSpec, DraftTask, UncertaintySeverity, Certainty
from .models import CompileDiagnostic
from .repair_models import RepairChange, RepairConfidence
from .error_classifier import ErrorClassifier

class RepairStrategies:
    def __init__(self, error_classifier: ErrorClassifier):
        self.error_classifier = error_classifier

    def apply_deterministic_repairs(self, draft: DraftSpec, diagnostics: List[CompileDiagnostic]) -> Tuple[List[RepairChange], List[str]]:
        changes = []
        fixed_errors = []

        # Sort diagnostics to avoid indexing issues if we were deleting (we aren't currently)
        for diag in diagnostics:
            failure_type = self.error_classifier.classify(diag)

            if failure_type == "missing_required_field":
                if diag.code == "missing_title":
                    old_val = draft.title
                    draft.title = "Untitled Draft"
                    changes.append(RepairChange("title", old_val, draft.title, "Injected default title"))
                    fixed_errors.append(diag.code)
                elif diag.code == "missing_task_id":
                    if diag.field_path and diag.field_path.startswith("tasks["):
                        try:
                            idx = int(diag.field_path.split("[")[1].split("]")[0])
                            old_id = draft.tasks[idx].id
                            new_id = f"task_{idx}_{uuid.uuid4().hex[:4]}"
                            draft.tasks[idx].id = new_id
                            changes.append(RepairChange(diag.field_path, old_id, new_id, "Generated deterministic task ID"))
                            fixed_errors.append(diag.code)
                        except (IndexError, ValueError):
                            pass

            elif failure_type == "duplicate_task_id":
                 if diag.field_path and diag.field_path.startswith("tasks["):
                        try:
                            idx = int(diag.field_path.split("[")[1].split("]")[0])
                            old_id = draft.tasks[idx].id
                            new_id = f"{old_id}_dup_{idx}"
                            draft.tasks[idx].id = new_id
                            changes.append(RepairChange(diag.field_path, old_id, new_id, "Renamed duplicate task ID"))
                            fixed_errors.append(diag.code)
                        except (IndexError, ValueError):
                            pass

            elif failure_type == "invalid_dependency":
                if diag.field_path and diag.field_path.startswith("tasks["):
                    try:
                        idx = int(diag.field_path.split("[")[1].split("]")[0])
                        valid_ids = {t.id for t in draft.tasks if t.id}
                        old_deps = list(draft.tasks[idx].depends_on)
                        new_deps = [d for d in old_deps if d in valid_ids]
                        if len(old_deps) != len(new_deps):
                            draft.tasks[idx].depends_on = new_deps
                            changes.append(RepairChange(diag.field_path, old_deps, new_deps, "Removed invalid dependencies"))
                            fixed_errors.append(diag.code)
                    except (IndexError, ValueError):
                        pass

        return changes, fixed_errors

    def apply_llm_repairs(self, draft: DraftSpec, diagnostics: List[CompileDiagnostic], ollama_service: Any) -> Tuple[List[RepairChange], List[str]]:
        # In a real system, this would call Ollama with a prompt.
        # For Demo10, we'll simulate LLM-assisted fixes for specific known failure types
        # that are hard to fix deterministically.

        changes = []
        fixed_errors = []

        for diag in diagnostics:
            failure_type = self.error_classifier.classify(diag)

            if failure_type == "unknown_task_type":
                if diag.field_path and diag.field_path.startswith("tasks["):
                    try:
                        idx = int(diag.field_path.split("[")[1].split("]")[0])
                        old_type = draft.tasks[idx].type
                        # LLM simulation: map "make_file" -> "generate_file"
                        if old_type == "make_file":
                            new_type = "generate_file"
                            draft.tasks[idx].type = new_type
                            changes.append(RepairChange(diag.field_path, old_type, new_type, "LLM mapped unknown type to 'generate_file'"))
                            fixed_errors.append(diag.code)
                    except (IndexError, ValueError):
                        pass

            elif failure_type == "blocking_uncertainty_present":
                # LLM simulation: resolve a blocking uncertainty if possible
                # Find the uncertainty
                for u in draft.uncertainties:
                    if u.field_path == diag.field_path and (u.severity == UncertaintySeverity.BLOCKING or u.severity.value == "blocking"):
                        # Propose a resolution
                        u.severity = UncertaintySeverity.INFO
                        u.message = f"[AUTO-RESOLVED] {u.message}"
                        changes.append(RepairChange(f"uncertainties[{u.code}]", "BLOCKING", "INFO", f"LLM resolved blocking uncertainty: {u.code}"))
                        fixed_errors.append(diag.code)
                        break

        return changes, fixed_errors

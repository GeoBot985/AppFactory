from __future__ import annotations
from typing import List, Dict, Any
from .models import CompileDiagnostic

class ErrorClassifier:
    def classify(self, diagnostic: CompileDiagnostic) -> str:
        code = diagnostic.code

        if code in ["missing_title", "missing_task_id"]:
            return "missing_required_field"

        if code == "duplicate_task_id":
            return "duplicate_task_id"

        if code == "unknown_task_type":
            return "unknown_task_type"

        if code == "invalid_dependency":
            return "invalid_dependency"

        if code == "dependency_cycle":
            return "dependency_cycle"

        if code == "blocking_uncertainty":
            return "blocking_uncertainty_present"

        if code == "policy_block":
            return "policy_violation_scope"

        if code == "unsupported_version":
            return "unsupported_feature"

        return "other"

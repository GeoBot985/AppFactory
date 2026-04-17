import os
from pathlib import Path
from typing import List, Dict, Any
from services.planner.models import Step

class ContractEvaluator:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def evaluate_preconditions(self, step: Step) -> bool:
        # v1: minimal deterministic checks
        for condition in step.contract.preconditions:
            if condition == "path_valid":
                if not self._is_path_safe(step.target):
                    return False
            elif condition == "file_exists":
                if not (self.workspace_root / step.target).exists():
                    return False
            elif condition == "file_not_exists":
                if (self.workspace_root / step.target).exists():
                    return False
            # Add more conditions as needed
        return True

    def evaluate_postconditions(self, step: Step, outputs: Dict[str, Any]) -> bool:
        # v1: minimal deterministic checks
        for condition in step.contract.postconditions:
            if condition == "file_created":
                if not (self.workspace_root / step.target).exists():
                    return False
            elif condition == "content_matches":
                # placeholder for content matching logic
                pass
            # Add more conditions as needed
        return True

    def _is_path_safe(self, path: str) -> bool:
        if not path:
            return False

        # Block absolute paths
        if os.path.isabs(path):
            return False

        # Ensure it stays within workspace_root
        try:
            full_path = (self.workspace_root / path).resolve()
            return str(full_path).startswith(str(self.workspace_root.resolve()))
        except Exception:
            return False

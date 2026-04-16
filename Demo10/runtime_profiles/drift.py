from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from .models import RuntimeProfile, DriftPolicyMode

class DriftDetector:
    def detect(
        self,
        current_fingerprint: Dict[str, str],
        baseline_fingerprint: Dict[str, str]
    ) -> List[Dict[str, str]]:
        diffs = []

        # Check python version
        curr_ver = current_fingerprint.get("python_version")
        base_ver = baseline_fingerprint.get("python_version")
        if curr_ver != base_ver:
            diffs.append({
                "type": "PYTHON_VERSION_MISMATCH",
                "expected": base_ver,
                "actual": curr_ver
            })

        # Check interpreter path
        curr_path = current_fingerprint.get("interpreter_path")
        base_path = baseline_fingerprint.get("interpreter_path")
        if curr_path != base_path:
            diffs.append({
                "type": "INTERPRETER_PATH_MISMATCH",
                "expected": base_path,
                "actual": curr_path
            })

        return diffs

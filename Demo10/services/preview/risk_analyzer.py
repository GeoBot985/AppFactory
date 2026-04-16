from __future__ import annotations
from typing import List, Dict, Any
from .impact_model import ImpactPreview, RiskLevel, ImpactSummary, FileDiff

class RiskAnalyzer:
    def __init__(self, critical_files: List[str] = None):
        self.critical_files = critical_files or ["main.py", "app.py", "root.py"]

    def analyze(self, preview: ImpactPreview) -> None:
        reasons = []
        summary = preview.summary

        # 1. Modifying critical entrypoints
        for diff in preview.file_diffs:
            if any(diff.path.endswith(crit) for crit in self.critical_files):
                reasons.append(f"Modifying critical entrypoint: {diff.path}")
                summary.has_critical_changes = True

        # 2. Modifying many files
        if summary.total_files > 5:
            reasons.append(f"Modifying many files ({summary.total_files})")

        # 3. Deleting files
        if summary.files_deleted > 0:
            reasons.append(f"Deleting {summary.files_deleted} file(s)")

        # 4. Large diff size
        for diff in preview.file_diffs:
            if diff.is_large_change:
                reasons.append(f"Large change in {diff.path}")

        # 5. Modifying test files
        test_mods = [d for d in preview.file_diffs if "test" in d.path.lower()]
        if test_mods:
            reasons.append(f"Modifying {len(test_mods)} test file(s)")

        preview.risk_reasons = reasons

        if not reasons:
            preview.risk_level = RiskLevel.LOW
        elif any("critical" in r or "Deleting" in r for r in reasons) or len(reasons) >= 3:
            preview.risk_level = RiskLevel.HIGH
        else:
            preview.risk_level = RiskLevel.MEDIUM

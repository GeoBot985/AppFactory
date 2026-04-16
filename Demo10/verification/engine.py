from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List
from .models import CheckStatus, VerificationReport, CheckResult
from .checks import VerificationExecutor

class VerificationEngine:
    def __init__(self, project_root: Path):
        self.executor = VerificationExecutor(project_root)

    def run(self, verification_data: Dict[str, Any], task_results: List[Any]) -> VerificationReport:
        checks_data = verification_data.get("checks", [])
        results: List[CheckResult] = []

        for check_def in checks_data:
            result = self.executor.execute_check(check_def, task_results)
            results.append(result)

        summary = {
            "total": len(results),
            "passed": sum(1 for r in results if r.status == CheckStatus.PASS),
            "failed": sum(1 for r in results if r.status == CheckStatus.FAIL),
            "warned": sum(1 for r in results if r.status == CheckStatus.WARN),
            "errored": sum(1 for r in results if r.status == CheckStatus.ERROR),
        }

        return VerificationReport(checks=results, summary=summary)

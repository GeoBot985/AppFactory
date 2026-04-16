import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from .models import HealthStatus, HealthSeverity, DashboardSummary

class HealthEvaluator:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.ops_dir = project_root / "runtime_data" / "ops"

    def evaluate(self) -> HealthStatus:
        summary_file = self.ops_dir / "dashboard_summary.json"
        summary = DashboardSummary()
        if summary_file.exists():
            with summary_file.open("r") as f:
                data = json.load(f)
                summary = DashboardSummary(**data)

        components = {
            "queues": "OK",
            "runs": "OK",
            "approvals": "OK",
            "regression": "OK",
            "ledger": "OK"
        }

        banners = []

        # 1. Approvals
        if summary.approval_pending_runs > 5:
            components["approvals"] = "WARN"
            banners.append("APPROVAL_BACKLOG")

        # 2. Regression
        if summary.failing_regression_suites > 0:
            components["regression"] = "FAIL"
            banners.append("REGRESSION_FAILING")

        # 3. Interrupted Runs
        if summary.interrupted_runs > 0:
            banners.append("RECOVERY_PENDING")

        # 4. Overall status
        overall = "OK"
        if any(v == "FAIL" for v in components.values()):
            overall = "FAIL"
        elif any(v == "WARN" for v in components.values()):
            overall = "WARN"

        # Update summary with banners
        summary.banners = banners
        self._save_summary(summary)

        status = HealthStatus(
            status=overall,
            generated_at=datetime.now().isoformat(),
            components=components
        )
        self._save_health(status)
        return status

    def _save_summary(self, summary: DashboardSummary):
        with (self.ops_dir / "dashboard_summary.json").open("w") as f:
            json.dump(summary.to_dict(), f, indent=2)

    def _save_health(self, status: HealthStatus):
        with (self.ops_dir / "health_status.json").open("w") as f:
            json.dump(status.to_dict(), f, indent=2)

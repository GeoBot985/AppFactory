import json
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from .models import Metric, DailyAggregate

class TelemetryQuery:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.telemetry_dir = workspace_root / "runtime_data" / "telemetry"
        self.metrics_dir = self.telemetry_dir / "metrics"
        self.aggregates_file = self.telemetry_dir / "aggregates" / "daily_summary.json"

    def get_metric(self, name: str, days: int = 7) -> List[Metric]:
        metrics = []
        end_date = date.today()
        for i in range(days):
            target_date = end_date - timedelta(days=i)
            date_str = target_date.strftime("%Y-%m-%d")
            metric_file = self.metrics_dir / f"{date_str}.jsonl"

            if metric_file.exists():
                with open(metric_file, "r") as f:
                    for line in f:
                        m = Metric.model_validate_json(line)
                        if m.name == name:
                            metrics.append(m)
        return sorted(metrics, key=lambda x: x.timestamp)

    def get_daily_aggregate(self, target_date: date) -> Optional[DailyAggregate]:
        if not self.aggregates_file.exists():
            return None

        with open(self.aggregates_file, "r") as f:
            summaries = json.load(f)

        date_str = target_date.strftime("%Y-%m-%d")
        if date_str in summaries:
            return DailyAggregate(**summaries[date_str])
        return None

    def get_summary_stats(self, days: int = 7) -> Dict[str, Any]:
        """Aggregate multiple days into a single summary."""
        if not self.aggregates_file.exists():
            return {}

        with open(self.aggregates_file, "r") as f:
            summaries = json.load(f)

        end_date = date.today()
        targets = []
        for i in range(days):
            d_str = (end_date - timedelta(days=i)).strftime("%Y-%m-%d")
            if d_str in summaries:
                targets.append(DailyAggregate(**summaries[d_str]))

        if not targets:
            return {}

        total_runs = sum(t.runs_total for t in targets)
        total_failed = sum(t.runs_failed for t in targets)
        total_completed = sum(t.runs_completed for t in targets)

        return {
            "runs_total": total_runs,
            "runs_failed": total_failed,
            "runs_completed": total_completed,
            "failure_rate": total_failed / (total_completed + total_failed) if (total_completed + total_failed) > 0 else 0,
            "verification_pass": sum(t.verification_pass for t in targets),
            "verification_warn": sum(t.verification_warn for t in targets),
            "verification_fail": sum(t.verification_fail for t in targets),
            "promotions_approved": sum(t.promotions_approved for t in targets),
            "promotions_rejected": sum(t.promotions_rejected for t in targets),
        }

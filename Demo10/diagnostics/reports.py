import json
from pathlib import Path
from datetime import datetime, date
from typing import List, Dict, Any
from .models import FailurePattern, RootCauseSummary
from .patterns import PatternManager

class DiagnosticsReporter:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.diagnostics_dir = workspace_root / "runtime_data" / "diagnostics"
        self.reports_dir = self.diagnostics_dir / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.pattern_manager = PatternManager(workspace_root)

    def generate_daily_report(self, target_date: date):
        date_str = target_date.strftime("%Y-%m-%d")
        patterns = self.pattern_manager.get_patterns()

        # Filter patterns seen on this day if possible,
        # but Spec 052 reports usually aggregate overall state or daily deltas.
        # For v1, let's provide a summary of current top patterns and root causes.

        root_cause_counts = {}
        affected_runs_by_rc = {}

        for p in patterns:
            rc = p.root_cause_id
            root_cause_counts[rc] = root_cause_counts.get(rc, 0) + p.occurrences
            if rc not in affected_runs_by_rc:
                affected_runs_by_rc[rc] = set()
            affected_runs_by_rc[rc].update(p.affected_runs)

        rc_summaries = [
            RootCauseSummary(
                root_cause=rc,
                count=count,
                affected_runs=list(affected_runs_by_rc[rc])
            )
            for rc, count in root_cause_counts.items()
        ]

        report = {
            "date": date_str,
            "generated_at": datetime.now().isoformat(),
            "root_cause_summaries": [s.model_dump() for s in rc_summaries],
            "top_patterns": [p.model_dump() for p in sorted(patterns, key=lambda x: x.impact_score, reverse=True)[:10]]
        }

        report_path = self.reports_dir / f"daily_diagnostics_{date_str}.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        # Also update a latest pointer or combined file if needed
        latest_path = self.reports_dir / "latest_diagnostics.json"
        with open(latest_path, "w") as f:
            json.dump(report, f, indent=2)

        return report

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from .models import FailurePattern, RootCauseSummary, FailureInstance
from .patterns import PatternManager

class DiagnosticsQuery:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.diagnostics_dir = workspace_root / "runtime_data" / "diagnostics"
        self.pattern_manager = PatternManager(workspace_root)

    def get_root_causes(self, date_range: Optional[tuple[datetime, datetime]] = None) -> List[RootCauseSummary]:
        patterns = self.pattern_manager.get_patterns()

        if date_range:
            start, end = date_range
            # Note: affected_runs might still contain runs outside range if they belong to the same pattern
            # For v1, we filter patterns based on their last_seen/first_seen overlap with range.
            patterns = [p for p in patterns if p.last_seen >= start and p.first_seen <= end]

        rc_map = {}
        affected_runs = {}

        for p in patterns:
            rc = p.root_cause_id
            rc_map[rc] = rc_map.get(rc, 0) + p.occurrences
            if rc not in affected_runs:
                affected_runs[rc] = set()
            affected_runs[rc].update(p.affected_runs)

        return [
            RootCauseSummary(root_cause=rc, count=count, affected_runs=list(affected_runs[rc]))
            for rc, count in rc_map.items()
        ]

    def get_failure_patterns(self, limit: int = 20, date_range: Optional[tuple[datetime, datetime]] = None) -> List[FailurePattern]:
        patterns = self.pattern_manager.get_patterns()

        if date_range:
            start, end = date_range
            patterns = [p for p in patterns if p.last_seen >= start and p.first_seen <= end]

        return sorted(patterns, key=lambda x: x.impact_score, reverse=True)[:limit]

    def get_top_failures(self, limit: int = 5) -> List[FailurePattern]:
        return self.get_failure_patterns(limit=limit)

    def get_run_diagnostics(self, run_id: str) -> Dict[str, Any]:
        instances_path = self.diagnostics_dir / "instances.json"
        if not instances_path.exists():
            return {"run_id": run_id, "failures": []}

        with open(instances_path, "r") as f:
            try:
                all_instances = json.load(f)
            except:
                return {"run_id": run_id, "failures": []}

        run_instances = [i for i in all_instances if i["run_id"] == run_id]

        return {
            "run_id": run_id,
            "failures": run_instances,
            "failure_count": len(run_instances)
        }

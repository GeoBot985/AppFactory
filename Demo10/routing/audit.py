import json
import uuid
from pathlib import Path
from typing import List, Dict, Any
from .models import RoutingDecision, MacroMatch, RoutingRule

class RoutingAuditor:
    def __init__(self, workspace_root: Path):
        self.audit_dir = workspace_root / "runtime_data" / "routing"
        self.decisions_dir = self.audit_dir / "decisions"
        self.matches_dir = self.audit_dir / "matches"

        self.decisions_dir.mkdir(parents=True, exist_ok=True)
        self.matches_dir.mkdir(parents=True, exist_ok=True)

    def record_decision(self, decision: RoutingDecision, matches: List[MacroMatch], rules: List[RoutingRule]):
        decision_path = self.decisions_dir / f"{decision.decision_id}.json"
        with open(decision_path, "w") as f:
            json.dump(decision.to_dict(), f, indent=2)

        matches_path = self.matches_dir / f"{decision.decision_id}.json"
        with open(matches_path, "w") as f:
            json.dump({
                "matches": [m.to_dict() for m in matches],
                "rules_snapshot": [r.to_dict() for r in rules]
            }, f, indent=2)

    def record_rules_snapshot(self, rules: List[RoutingRule]):
        snapshot_path = self.audit_dir / "rules_snapshot.json"
        with open(snapshot_path, "w") as f:
            json.dump([r.to_dict() for r in rules], f, indent=2)

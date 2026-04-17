import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from .models import RoutingRule, GoalSignature

class RuleManager:
    def __init__(self, workspace_root: Path):
        self.rules_path = workspace_root / "runtime_data" / "routing" / "rules.json"
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        self._rules: List[RoutingRule] = []

    def load_rules(self) -> List[RoutingRule]:
        if not self.rules_path.exists():
            return []

        with open(self.rules_path, "r") as f:
            data = json.load(f)
            self._rules = [RoutingRule(**r) for r in data]
        return self._rules

    def save_rules(self, rules: List[RoutingRule]):
        self._rules = rules
        with open(self.rules_path, "w") as f:
            json.dump([r.to_dict() for r in rules], f, indent=2)

    def evaluate_rule(self, rule: RoutingRule, sig: GoalSignature) -> bool:
        pattern = rule.goal_pattern

        # operation_types exact match or subset
        if "operation_types" in pattern:
            req_ops = pattern["operation_types"]
            if not all(op in sig.operation_types for op in req_ops):
                return False

        # target pattern matches (very basic glob-ish match)
        if "target_pattern" in pattern:
            pat = pattern["target_pattern"].lower()
            if pat.startswith("*."):
                ext = pat[1:]
                if not any(t.endswith(ext) for t in sig.targets):
                    return False
            elif pat not in sig.targets:
                return False

        # constraints
        if "required_constraints" in pattern:
            req_c = pattern["required_constraints"]
            if not all(c.lower() in sig.constraints for c in req_c):
                return False

        # intent tokens
        if "required_tokens" in pattern:
            req_t = pattern["required_tokens"]
            if not all(t.lower() in sig.intent_tokens for t in req_t):
                return False

        return True

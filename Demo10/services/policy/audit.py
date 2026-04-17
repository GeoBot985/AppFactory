import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from .models import PromotionDecision, PromotionHistory, Environment

class PromotionAuditService:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.promotions_dir = workspace_root / "runtime_data" / "promotions"
        self.history_dir = workspace_root / "runtime_data" / "promotion_history"

        self.promotions_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def record_decision(self, decision: PromotionDecision, candidate_info: dict):
        candidate_dir = self.promotions_dir / decision.candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)

        record = {
            "candidate_id": decision.candidate_id,
            "source_environment": candidate_info.get("source_environment"),
            "target_environment": candidate_info.get("target_environment"),
            "decision": decision.decision,
            "reasons": decision.reasons,
            "system_version": candidate_info.get("system_version"),
            "verification_suite_id": candidate_info.get("verification_suite_id"),
            "verification_result_id": candidate_info.get("verification_result_id"),
            "timestamp": decision.evaluated_at.isoformat()
        }

        with open(candidate_dir / "promotion.json", "w") as f:
            json.dump(record, f, indent=2)

        self._update_history(candidate_info.get("system_version"), decision, candidate_info.get("target_environment"))

    def _update_history(self, system_version: str, decision: PromotionDecision, target_env: Environment):
        history_file = self.history_dir / f"{system_version}.json"

        if history_file.exists():
            with open(history_file, "r") as f:
                data = json.load(f)
                history = PromotionHistory(
                    system_version=data["system_version"],
                    environments_reached=data["environments_reached"],
                    decisions=[self._parse_decision(d) for d in data["decisions"]]
                )
        else:
            history = PromotionHistory(
                system_version=system_version,
                environments_reached=[],
                decisions=[]
            )

        history.decisions.append(decision)
        if decision.decision in ["approved", "approved_with_warnings", "approved_with_override"]:
            if target_env not in history.environments_reached:
                history.environments_reached.append(target_env)

        with open(history_file, "w") as f:
            json.dump({
                "system_version": history.system_version,
                "environments_reached": history.environments_reached,
                "decisions": [self._serialize_decision(d) for d in history.decisions]
            }, f, indent=2)

    def _serialize_decision(self, d: PromotionDecision) -> dict:
        return {
            "candidate_id": d.candidate_id,
            "decision": d.decision,
            "reasons": d.reasons,
            "policy_snapshot": d.policy_snapshot,
            "evaluated_at": d.evaluated_at.isoformat()
        }

    def _parse_decision(self, data: dict) -> PromotionDecision:
        return PromotionDecision(
            candidate_id=data["candidate_id"],
            decision=data["decision"],
            reasons=data["reasons"],
            policy_snapshot=data["policy_snapshot"],
            evaluated_at=datetime.fromisoformat(data["evaluated_at"])
        )

    def get_history(self, system_version: str) -> Optional[PromotionHistory]:
        history_file = self.history_dir / f"{system_version}.json"
        if not history_file.exists():
            return None

        with open(history_file, "r") as f:
            data = json.load(f)
            return PromotionHistory(
                system_version=data["system_version"],
                environments_reached=data["environments_reached"],
                decisions=[self._parse_decision(d) for d in data["decisions"]]
            )

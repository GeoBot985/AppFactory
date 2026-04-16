import json
import os
from pathlib import Path
from typing import List
from datetime import datetime
from .models import PolicyEvaluationResult

class PolicyLogService:
    def __init__(self, project_root: Path):
        self.log_dir = project_root / "runtime_data" / "policy" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.global_log = self.log_dir / "policy_audit.jsonl"

    def log_decision(self, result: PolicyEvaluationResult):
        entry = result.to_dict()

        # Append to global audit log
        with open(self.global_log, "a") as f:
            f.write(json.dumps(entry) + "\n")

        # Also log to run-specific directory if applicable
        if result.entity_id.startswith("run_") or result.entity_id.startswith("slot_"):
            run_log_dir = self.log_dir / result.entity_id
            run_log_dir.mkdir(parents=True, exist_ok=True)
            run_log_file = run_log_dir / "policy_decisions.jsonl"
            with open(run_log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")

    def get_logs_for_entity(self, entity_id: str) -> List[dict]:
        run_log_file = self.log_dir / entity_id / "policy_decisions.jsonl"
        if not run_log_file.exists():
            return []

        logs = []
        with open(run_log_file, "r") as f:
            for line in f:
                logs.append(json.loads(line))
        return logs

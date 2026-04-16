import json
from pathlib import Path
from typing import List, Dict, Any

class ConsistencyIssue:
    def __init__(self, issue_type: str, description: str, entity_id: str = ""):
        self.issue_type = issue_type
        self.description = description
        self.entity_id = entity_id

    def to_dict(self):
        return {
            "type": self.issue_type,
            "description": self.description,
            "entity_id": self.entity_id
        }

class ConsistencyChecker:
    def __init__(self, storage_root: Path, ledger_service: Any):
        self.storage_root = storage_root
        self.ledger_service = ledger_service
        self.runs_dir = storage_root / "runs"

    def check_consistency(self) -> List[ConsistencyIssue]:
        issues = []
        current_runs = self.ledger_service.load_current_runs()

        # 1. Check if run artifacts exist for ledger entries
        for run_id, data in current_runs.items():
            workspace = data.get("execution_workspace")
            if workspace and not Path(workspace).exists():
                # Workspace might have been cleaned up by retention policy, so check if it's terminal
                from .models import RunState
                terminal_states = {
                    RunState.COMPLETED.value,
                    RunState.FAILED.value,
                    RunState.PROMOTED.value,
                    RunState.DISCARDED.value
                }
                if data.get("state") not in terminal_states:
                    issues.append(ConsistencyIssue(
                        "MISSING_RUN_ARTIFACT_DIR",
                        f"Workspace for run {run_id} is missing but run is not terminal",
                        run_id
                    ))

        # 2. Check for orphaned run directories (discovery)
        if self.runs_dir.exists():
            run_folders = [f for f in self.runs_dir.iterdir() if f.is_dir()]
            for folder in run_folders:
                # This is a bit complex because run_id != folder name exactly
                # But we can check if any ledger entry points to it
                found = False
                for data in current_runs.values():
                    if data.get("execution_workspace") and Path(data["execution_workspace"]) == folder:
                        found = True
                        break
                    # Also check audit logs
                    if folder.name.startswith("20") and "_slot_" in folder.name:
                         # Likely a standard audit run folder
                         found = True
                         break

                if not found:
                     issues.append(ConsistencyIssue(
                         "ORPHANED_RUN_DIR",
                         f"Folder {folder.name} is not referenced in the ledger",
                         folder.name
                     ))

        return issues

    def persist_consistency_report(self, issues: List[ConsistencyIssue]):
        report_file = self.storage_root / "runtime_data" / "run_ledger" / "consistency_report.json"
        with report_file.open("w") as f:
            json.dump([issue.to_dict() for issue in issues], f, indent=2)

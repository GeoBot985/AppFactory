import json
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional
from .models import RunState, RunMetadata

class InterruptionCategory(Enum):
    RESUMABLE_AT_PHASE_BOUNDARY = "RESUMABLE_AT_PHASE_BOUNDARY"
    RESTART_REQUIRED = "RESTART_REQUIRED"
    NON_RESUMABLE = "NON_RESUMABLE"
    LEDGER_INCONSISTENT = "LEDGER_INCONSISTENT"

class RecoveryAction(Enum):
    RESUME = "RESUME"
    RESTART = "RESTART"
    SKIP = "SKIP"
    MANUAL = "MANUAL"

class RecoveryPlanItem:
    def __init__(self, run_id: str, category: InterruptionCategory, recommended_action: RecoveryAction, reason: str):
        self.run_id = run_id
        self.category = category
        self.recommended_action = recommended_action
        self.reason = reason

    def to_dict(self):
        return {
            "run_id": self.run_id,
            "category": self.category.value,
            "recommended_action": self.recommended_action.value,
            "reason": self.reason
        }

class RecoveryService:
    def __init__(self, storage_root: Path, ledger_service: Any):
        self.storage_root = storage_root
        self.ledger_service = ledger_service

    def scan_for_interrupted_runs(self) -> List[RecoveryPlanItem]:
        current_runs = self.ledger_service.load_current_runs()
        plan = []

        terminal_states = {
            RunState.COMPLETED.value,
            RunState.COMPLETED_WITH_WARNINGS.value,
            RunState.PARTIAL_FAILURE.value,
            RunState.FAILED.value,
            RunState.PROMOTED.value,
            RunState.DISCARDED.value,
            RunState.REPLAY_COMPLETED.value,
            RunState.REPLAY_FAILED.value
        }

        for run_id, data in current_runs.items():
            state = data.get("state")
            if state not in terminal_states and state != RunState.INTERRUPTED.value:
                # Classify
                item = self._classify_interruption(run_id, data)
                plan.append(item)

        return plan

    def _classify_interruption(self, run_id: str, data: Dict[str, Any]) -> RecoveryPlanItem:
        state = data.get("state")
        workspace = data.get("execution_workspace")
        manifest = data.get("source_snapshot_manifest")

        # Simple classification logic
        if not workspace or not Path(workspace).exists():
            return RecoveryPlanItem(
                run_id,
                InterruptionCategory.NON_RESUMABLE,
                RecoveryAction.SKIP,
                "Execution workspace missing"
            )

        if state in {RunState.EXECUTING.value, RunState.VERIFYING.value, RunState.STRUCTURAL_VALIDATING.value}:
             if manifest and Path(manifest).exists():
                 return RecoveryPlanItem(
                     run_id,
                     InterruptionCategory.RESUMABLE_AT_PHASE_BOUNDARY,
                     RecoveryAction.RESUME,
                     f"Interrupted during {state}, resumable from phase boundary"
                 )
             else:
                 return RecoveryPlanItem(
                     run_id,
                     InterruptionCategory.RESTART_REQUIRED,
                     RecoveryAction.RESTART,
                     "Snapshot manifest missing, restart required"
                 )

        return RecoveryPlanItem(
            run_id,
            InterruptionCategory.RESTART_REQUIRED,
            RecoveryAction.RESTART,
            f"Interrupted in state {state}"
        )

    def persist_recovery_plan(self, plan: List[RecoveryPlanItem]):
        plan_file = self.storage_root / "runtime_data" / "run_ledger" / "recovery_plan.json"
        with plan_file.open("w") as f:
            json.dump([item.to_dict() for item in plan], f, indent=2)

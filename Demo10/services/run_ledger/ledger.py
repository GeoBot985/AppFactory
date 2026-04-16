import json
import os
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from .models import LedgerEvent, RunMetadata

class LedgerService:
    def __init__(self, storage_root: Path):
        self.storage_root = storage_root
        self.ledger_dir = storage_root / "runtime_data" / "run_ledger"
        self.ledger_dir.mkdir(parents=True, exist_ok=True)

        self.events_file = self.ledger_dir / "events.jsonl"
        self.current_runs_file = self.ledger_dir / "current_runs.json"

        self._seq_no = self._get_last_seq_no()

    def _get_last_seq_no(self) -> int:
        if not self.events_file.exists():
            return 0
        try:
            with self.events_file.open("r") as f:
                lines = f.readlines()
                if not lines:
                    return 0
                last_line = lines[-1]
                event = json.loads(last_line)
                return event.get("seq_no", 0)
        except Exception:
            return 0

    def record_event(self, entity_type: str, entity_id: str, event_type: str,
                     new_state: str, previous_state: Optional[str] = None,
                     run_id: Optional[str] = None, queue_id: Optional[str] = None,
                     slot_id: Optional[str] = None, payload: Optional[dict] = None,
                     trigger_ops_update: bool = True) -> LedgerEvent:
        self._seq_no += 1
        event = LedgerEvent(
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            previous_state=previous_state,
            new_state=new_state,
            timestamp=datetime.now().isoformat(),
            run_id=run_id,
            queue_id=queue_id,
            slot_id=slot_id,
            seq_no=self._seq_no,
            payload=payload or {}
        )

        # 1. Append to event log
        with self.events_file.open("a") as f:
            f.write(json.dumps(event.to_dict()) + "\n")
            f.flush()
            os.fsync(f.fileno())

        # 2. Trigger incremental ops update (SPEC 018 Mode A)
        if trigger_ops_update:
            try:
                from ops.ops_service import OpsService
                from ops.health import HealthEvaluator
                ops = OpsService(self.storage_root)
                # For now, simple rebuild of relevant indices on any event
                # In production this would be more granular
                ops.rebuild_all_indices()
                health = HealthEvaluator(self.storage_root)
                health.evaluate()
            except Exception as e:
                # Ops failure must not corrupt ledger truth
                print(f"Ops update failed: {e}")

        return event

    def update_run_metadata(self, metadata: RunMetadata):
        # Atomic update of current state store
        current_state = self.load_current_runs()
        current_state[metadata.run_id] = metadata.to_dict()

        temp_file = self.current_runs_file.with_suffix(".tmp")
        with temp_file.open("w") as f:
            json.dump(current_state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        temp_file.replace(self.current_runs_file)

    def load_current_runs(self) -> Dict[str, Any]:
        if not self.current_runs_file.exists():
            return {}
        try:
            with self.current_runs_file.open("r") as f:
                return json.load(f)
        except Exception:
            return {}

    def get_run_metadata(self, run_id: str) -> Optional[RunMetadata]:
        runs = self.load_current_runs()
        data = runs.get(run_id)
        if not data:
            return None
        # Convert back from dict
        from .models import RunState
        return RunMetadata(
            run_id=data["run_id"],
            spec_id=data["spec_id"],
            queue_id=data["queue_id"],
            slot_id=data["slot_id"],
            state=RunState(data["state"]),
            execution_mode=data["execution_mode"],
            runtime_profile=data["runtime_profile"],
            source_policy=data["source_policy"],
            source_snapshot_manifest=data.get("source_snapshot_manifest"),
            execution_workspace=data.get("execution_workspace"),
            verification_report=data.get("verification_report"),
            promotion_report=data.get("promotion_report"),
            resume_policy=data.get("resume_policy", "restart_from_phase_boundary"),
            parent_run_id=data.get("parent_run_id"),
            restart_of_run_id=data.get("restart_of_run_id"),
            replay_of_run_id=data.get("replay_of_run_id"),
            created_at=data["created_at"],
            updated_at=data["updated_at"]
        )

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from .models import QueueDefinition, QueueState

class QueueStore:
    def __init__(self, storage_root: Path):
        self.storage_root = storage_root
        self.queues_dir = storage_root / "runtime_data" / "queues"
        self.queues_dir.mkdir(parents=True, exist_ok=True)

        self.current_queues_file = storage_root / "runtime_data" / "run_ledger" / "current_queues.json"
        self.current_queues_file.parent.mkdir(parents=True, exist_ok=True)

    def save_queue_definition(self, definition: QueueDefinition):
        queue_file = self.queues_dir / f"{definition.queue_id}.json"

        temp_file = queue_file.with_suffix(".tmp")
        with temp_file.open("w") as f:
            json.dump(definition.to_dict(), f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        temp_file.replace(queue_file)

        # Also update current_queues index
        self._update_current_queues(definition)

    def _update_current_queues(self, definition: QueueDefinition):
        current = self.load_current_queues()
        current[definition.queue_id] = {
            "queue_id": definition.queue_id,
            "state": definition.state.value,
            "updated_at": definition.created_at # simplified
        }

        temp_file = self.current_queues_file.with_suffix(".tmp")
        with temp_file.open("w") as f:
            json.dump(current, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        temp_file.replace(self.current_queues_file)

    def load_current_queues(self) -> Dict[str, Any]:
        if not self.current_queues_file.exists():
            return {}
        try:
            with self.current_queues_file.open("r") as f:
                return json.load(f)
        except Exception:
            return {}

    def get_queue_definition(self, queue_id: str) -> Optional[QueueDefinition]:
        queue_file = self.queues_dir / f"{queue_id}.json"
        if not queue_file.exists():
            return None
        try:
            with queue_file.open("r") as f:
                data = json.load(f)
                return QueueDefinition(
                    queue_id=data["queue_id"],
                    created_at=data["created_at"],
                    settings=data["settings"],
                    slots=data["slots"],
                    runtime_defaults=data["runtime_defaults"],
                    recovery_policy=data["recovery_policy"],
                    source_policy=data["source_policy"],
                    state=QueueState(data["state"])
                )
        except Exception:
            return None

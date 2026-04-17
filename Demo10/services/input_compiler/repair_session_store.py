from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
from .repair_models import RepairSession

class RepairSessionStore:
    def __init__(self, storage_dir: Path = Path("runtime_data/repair_sessions")):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, session: RepairSession):
        filepath = self.storage_dir / f"{session.session_id}.json"
        with filepath.open("w") as f:
            json.dump(session.to_dict(), f, indent=2)

    def load_session(self, session_id: str) -> Optional[RepairSession]:
        filepath = self.storage_dir / f"{session_id}.json"
        if not filepath.exists():
            return None

        # In a real implementation we would deserialize, but for Demo10
        # we might just return the dict or similar.
        with filepath.open("r") as f:
            return json.load(f)

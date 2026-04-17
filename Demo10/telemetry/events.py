import json
import os
from pathlib import Path
from datetime import datetime
from typing import Any, Dict
from .models import TelemetryEvent, TelemetryEventType

class TelemetryEmitter:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.telemetry_dir = workspace_root / "runtime_data" / "telemetry"
        self.events_dir = self.telemetry_dir / "events"
        self.events_dir.mkdir(parents=True, exist_ok=True)

    def emit(self, event_type: TelemetryEventType, payload: Dict[str, Any]):
        event = TelemetryEvent(event_type=event_type, payload=payload)
        self._store_event(event)
        return event

    def _store_event(self, event: TelemetryEvent):
        date_str = event.timestamp.strftime("%Y-%m-%d")
        file_path = self.events_dir / f"{date_str}.jsonl"

        try:
            with open(file_path, "a") as f:
                f.write(event.model_dump_json() + "\n")
        except Exception as e:
            # SPEC 051 Section 15: Telemetry failures must not break execution.
            print(f"TELEMETRY_WRITE_FAILED: {e}")

# Global emitter instance if needed, though usually better to pass it or instantiate where needed.
# For simplicity in integration, I'll provide a factory or just instantiate in the core classes.

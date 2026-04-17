from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional

class StageStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    AWAITING_USER = "awaiting_user"

@dataclass
class StageState:
    stage_name: str
    status: StageStatus = StageStatus.PENDING
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def mark_running(self):
        self.status = StageStatus.RUNNING
        self.start_time = datetime.now().isoformat()

    def mark_completed(self, outputs: Optional[Dict[str, Any]] = None):
        self.status = StageStatus.COMPLETED
        self.end_time = datetime.now().isoformat()
        if outputs:
            self.outputs.update(outputs)

    def mark_failed(self, error: str):
        self.status = StageStatus.FAILED
        self.end_time = datetime.now().isoformat()
        self.errors.append(error)

    def mark_blocked(self, reason: str):
        self.status = StageStatus.BLOCKED
        self.errors.append(reason)

    def mark_awaiting_user(self):
        self.status = StageStatus.AWAITING_USER

@dataclass
class OrchestratorRun:
    orchestrator_run_id: str
    request_text: str

    # Lineage IDs
    request_id: Optional[str] = None
    normalized_request_id: Optional[str] = None
    planning_skeleton_id: Optional[str] = None
    clarification_session_id: Optional[str] = None
    draft_spec_id: Optional[str] = None
    compiled_plan_id: Optional[str] = None
    preview_id: Optional[str] = None
    durable_run_id: Optional[str] = None
    apply_transaction_id: Optional[str] = None

    current_stage: str = "REQUEST_RECEIVED"
    stages: Dict[str, StageState] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "orchestrator_run_id": self.orchestrator_run_id,
            "request_text": self.request_text,
            "lineage": {
                "request_id": self.request_id,
                "normalized_request_id": self.normalized_request_id,
                "planning_skeleton_id": self.planning_skeleton_id,
                "clarification_session_id": self.clarification_session_id,
                "draft_spec_id": self.draft_spec_id,
                "compiled_plan_id": self.compiled_plan_id,
                "preview_id": self.preview_id,
                "durable_run_id": self.durable_run_id,
                "apply_transaction_id": self.apply_transaction_id
            },
            "current_stage": self.current_stage,
            "stages": {name: {
                "status": state.status.value,
                "start_time": state.start_time,
                "end_time": state.end_time,
                "errors": state.errors
            } for name, state in self.stages.items()}
        }

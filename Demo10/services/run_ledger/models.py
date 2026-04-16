from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Optional, List
from datetime import datetime

class RunState(Enum):
    CREATED = "CREATED"
    SNAPSHOT_PREPARING = "SNAPSHOT_PREPARING"
    SNAPSHOT_READY = "SNAPSHOT_READY"
    RUNTIME_RESOLVING = "RUNTIME_RESOLVING"
    READY_TO_EXECUTE = "READY_TO_EXECUTE"
    EXECUTING = "EXECUTING"
    STRUCTURAL_VALIDATING = "STRUCTURAL_VALIDATING"
    VERIFYING = "VERIFYING"
    PROMOTION_PENDING = "PROMOTION_PENDING"
    PROMOTED = "PROMOTED"
    DISCARDED = "DISCARDED"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    RECOVERY_PENDING = "RECOVERY_PENDING"
    REPLAYING = "REPLAYING"
    REPLAY_COMPLETED = "REPLAY_COMPLETED"
    REPLAY_FAILED = "REPLAY_FAILED"

class QueueSlotState(Enum):
    EMPTY = "EMPTY"
    LOADED = "LOADED"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED_BY_FAILURE = "PAUSED_BY_FAILURE"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    SKIPPED = "SKIPPED"
    REPLAYED = "REPLAYED"

class QueueState(Enum):
    CREATED = "CREATED"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    RECOVERY_PENDING = "RECOVERY_PENDING"

@dataclass
class RunMetadata:
    run_id: str
    spec_id: str
    queue_id: str
    slot_id: str
    state: RunState
    execution_mode: str
    runtime_profile: str
    source_policy: str
    source_snapshot_manifest: Optional[str] = None
    execution_workspace: Optional[str] = None
    verification_report: Optional[str] = None
    promotion_report: Optional[str] = None
    resume_policy: str = "restart_from_phase_boundary"
    parent_run_id: Optional[str] = None
    restart_of_run_id: Optional[str] = None
    replay_of_run_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "spec_id": self.spec_id,
            "queue_id": self.queue_id,
            "slot_id": self.slot_id,
            "state": self.state.value,
            "execution_mode": self.execution_mode,
            "runtime_profile": self.runtime_profile,
            "source_policy": self.source_policy,
            "source_snapshot_manifest": self.source_snapshot_manifest,
            "execution_workspace": self.execution_workspace,
            "verification_report": self.verification_report,
            "promotion_report": self.promotion_report,
            "resume_policy": self.resume_policy,
            "parent_run_id": self.parent_run_id,
            "restart_of_run_id": self.restart_of_run_id,
            "replay_of_run_id": self.replay_of_run_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

@dataclass
class LedgerEvent:
    event_id: str
    entity_type: str # run, queue, slot, replay, recovery
    entity_id: str
    event_type: str # state_transition, artifact_registered, recovery_started, replay_started, promotion_recorded
    previous_state: Optional[str]
    new_state: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    run_id: Optional[str] = None
    queue_id: Optional[str] = None
    slot_id: Optional[str] = None
    seq_no: int = 0
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "event_type": self.event_type,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "timestamp": self.timestamp,
            "run_id": self.run_id,
            "queue_id": self.queue_id,
            "slot_id": self.slot_id,
            "seq_no": self.seq_no,
            "payload": self.payload
        }

@dataclass
class QueueDefinition:
    queue_id: str
    created_at: str
    settings: dict
    slots: List[dict] # list of slot summaries
    runtime_defaults: dict
    recovery_policy: str
    source_policy: str
    state: QueueState = QueueState.CREATED

    def to_dict(self) -> dict:
        return {
            "queue_id": self.queue_id,
            "created_at": self.created_at,
            "settings": self.settings,
            "slots": self.slots,
            "runtime_defaults": self.runtime_defaults,
            "recovery_policy": self.recovery_policy,
            "source_policy": self.source_policy,
            "state": self.state.value
        }

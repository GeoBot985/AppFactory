from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any

from services.bundle_service import WorkingSetBundle
from services.selection_service import SelectionResult
from services.restore_service import RestoreResult
from services.bundle_edit_service import BundleEditRun
from verification.models import VerificationReport, RunSummary


QUEUE_SIZE = 10


@dataclass
class PipelineStage:
    name: str
    status: str = "pending"  # pending, running, completed, failed, skipped
    started_at: str = ""
    completed_at: str = ""
    last_message: str = ""
    message_history: list[str] = field(default_factory=list)


@dataclass
class QueueSlot:
    slot_index: int
    spec_text: str = ""
    status: str = "empty"
    compiled_plan: Optional[Any] = None
    started_at: str = ""
    completed_at: str = ""
    failure_reason: str = ""
    current_run_id: str = ""
    prior_run_ids: list[str] = field(default_factory=list)
    replay_run_ids: list[str] = field(default_factory=list)
    restart_run_ids: list[str] = field(default_factory=list)
    selection_result: SelectionResult | None = None
    bundle_result: WorkingSetBundle | None = None
    restore_result: RestoreResult | None = None
    llm_edit_run: BundleEditRun | None = None
    verification_report: VerificationReport | None = None
    run_summary: RunSummary | None = None
    notes_log_summary: list[str] = field(default_factory=list)
    pipeline_stages: list[PipelineStage] = field(default_factory=list)


@dataclass
class SpecQueueState:
    queue_slots: list[QueueSlot]
    queue_id: str = ""
    queue_status: str = "idle"
    active_slot_index: int = -1
    started_at: str = ""
    completed_at: str = ""
    stop_requested: bool = False
    completed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0


import uuid

class QueueService:
    def create_state(self) -> SpecQueueState:
        state = SpecQueueState(
            queue_slots=[QueueSlot(slot_index=i) for i in range(QUEUE_SIZE)],
            queue_id=f"q_{uuid.uuid4().hex[:8]}"
        )
        for slot in state.queue_slots:
            self._initialize_pipeline(slot)
        return state

    def _initialize_pipeline(self, slot: QueueSlot) -> None:
        slot.pipeline_stages = [
            PipelineStage(name="Spec Intake"),
            PipelineStage(name="Spec Parsing"),
            PipelineStage(name="Policy Check (Pre-Exec)"),
            PipelineStage(name="Runtime Environment"),
            PipelineStage(name="Impact Preview"),
            PipelineStage(name="Approval Gate"),
            PipelineStage(name="Task Execution"),
            PipelineStage(name="Structural Validation"),
            PipelineStage(name="Deterministic Verification"),
            PipelineStage(name="Regression Comparison"),
            PipelineStage(name="Outcome Synthesis"),
            PipelineStage(name="Policy Check (Pre-Promote)"),
            PipelineStage(name="Logging / Audit"),
        ]

    def load_specs(self, state: SpecQueueState, specs: list[str]) -> None:
        from services.input_compiler.models import CompileStatus
        import yaml
        for idx, slot in enumerate(state.queue_slots):
            spec = specs[idx].strip() if idx < len(specs) else ""

            # SPEC 041: Programmatic Gate Enforcement
            if spec:
                try:
                    data = yaml.safe_load(spec)
                    if isinstance(data, dict) and data.get("compile_status") == CompileStatus.BLOCKED.value:
                        raise ValueError(f"GATE_REJECTED: Cannot load blocked spec into slot {idx + 1}")
                except yaml.YAMLError:
                    pass # Not an IR, maybe legacy spec

            slot.spec_text = spec
            if slot.status == "running":
                slot.status = "ready" if spec else "empty"
            elif slot.status in {"empty", "ready", "failed", "completed", "skipped", "stopped"}:
                slot.status = "ready" if spec else "empty"
            slot.failure_reason = ""
            slot.selection_result = None
            slot.bundle_result = None
            slot.restore_result = None
            slot.llm_edit_run = None
            slot.verification_report = None
            slot.run_summary = None
            slot.started_at = ""
            slot.completed_at = ""
            slot.notes_log_summary = []
            self._initialize_pipeline(slot)

    def start(self, state: SpecQueueState) -> None:
        state.queue_status = "running"
        state.active_slot_index = -1
        state.started_at = self._now()
        state.completed_at = ""
        state.stop_requested = False
        state.completed_count = 0
        state.failed_count = 0
        state.skipped_count = 0
        for slot in state.queue_slots:
            slot.selection_result = None
            slot.bundle_result = None
            slot.restore_result = None
            slot.llm_edit_run = None
            slot.verification_report = None
            slot.run_summary = None
            slot.failure_reason = ""
            slot.started_at = ""
            slot.completed_at = ""
            slot.notes_log_summary = []
            slot.status = "ready" if slot.spec_text.strip() else "empty"

    def request_stop(self, state: SpecQueueState) -> None:
        state.stop_requested = True

    def mark_slot_running(self, state: SpecQueueState, slot: QueueSlot) -> None:
        slot.status = "running"
        slot.started_at = self._now()
        state.active_slot_index = slot.slot_index
        for stage in slot.pipeline_stages:
            stage.status = "pending"
            stage.started_at = ""
            stage.completed_at = ""
            stage.last_message = ""
            stage.message_history = []

    def update_stage_status(
        self,
        slot: QueueSlot,
        stage_name: str,
        status: str,
        message: str = "",
    ) -> None:
        for stage in slot.pipeline_stages:
            if stage.name == stage_name:
                stage.status = status
                if status == "running":
                    stage.started_at = self._now()
                elif status in {"completed", "failed", "skipped"}:
                    stage.completed_at = self._now()
                if message:
                    stage.last_message = message
                    stage.message_history.append(message)
                    if len(stage.message_history) > 8:
                        stage.message_history = stage.message_history[-8:]
                break

    def mark_slot_completed(self, state: SpecQueueState, slot: QueueSlot) -> None:
        slot.status = "completed"
        slot.completed_at = self._now()
        state.completed_count += 1

    def mark_slot_failed(self, state: SpecQueueState, slot: QueueSlot, reason: str) -> None:
        slot.status = "failed"
        slot.failure_reason = reason
        slot.completed_at = self._now()
        state.failed_count += 1

    def mark_slot_stopped(self, slot: QueueSlot, reason: str) -> None:
        slot.status = "stopped"
        slot.failure_reason = reason
        slot.completed_at = self._now()

    def finalize(self, state: SpecQueueState, status: str) -> None:
        state.queue_status = status
        state.completed_at = self._now()
        state.active_slot_index = -1

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from services.index_service import ArchitectureIndex
from services.bundle_service import WorkingSetBundle
from services.queue_service import SpecQueueState
from services.restore_service import RestoreResult, RestorePreview
from services.selection_service import SelectionResult
from services.bundle_edit_service import BundleEditRun


@dataclass
class RunState:
    model_name: str = ""
    project_folder: str = "not selected"
    spec_text: str = ""
    assembled_prompt: str = ""
    streamed_output_accumulator: list[str] = field(default_factory=list)
    final_response_text: str = ""
    started_at: str = ""
    completed_at: str = ""
    status: str = "idle"
    failure_reason: str = ""


@dataclass
class IndexState:
    latest_index: ArchitectureIndex | None = None
    status: str = "idle"
    failure_reason: str = ""


@dataclass
class SelectionState:
    latest_selection: SelectionResult | None = None
    status: str = "idle"
    failure_reason: str = ""


@dataclass
class BundleState:
    latest_bundle: WorkingSetBundle | None = None
    status: str = "idle"
    failure_reason: str = ""


@dataclass
class QueueRuntimeState:
    spec_queue: SpecQueueState | None = None
    status: str = "idle"
    failure_reason: str = ""


@dataclass
class RestoreState:
    latest_restore: RestoreResult | None = None
    latest_preview: RestorePreview | None = None
    status: str = "idle"
    failure_reason: str = ""


@dataclass
class BundleEditState:
    latest_edit_run: BundleEditRun | None = None
    status: str = "idle"
    failure_reason: str = ""


class RunStateService:
    def __init__(self) -> None:
        self.latest_run = RunState()
        self.index_state = IndexState()
        self.selection_state = SelectionState()
        self.bundle_state = BundleState()
        self.queue_runtime = QueueRuntimeState()
        self.restore_state = RestoreState()
        self.bundle_edit_state = BundleEditState()

    def begin_run(self, model_name: str, project_folder: str, spec_text: str, assembled_prompt: str) -> RunState:
        self.latest_run = RunState(
            model_name=model_name,
            project_folder=project_folder or "not selected",
            spec_text=spec_text,
            assembled_prompt=assembled_prompt,
            started_at=self._now(),
            status="running",
        )
        return self.latest_run

    def append_chunk(self, chunk: str) -> None:
        self.latest_run.streamed_output_accumulator.append(chunk)

    def complete_run(self) -> RunState:
        self.latest_run.final_response_text = "".join(self.latest_run.streamed_output_accumulator)
        self.latest_run.completed_at = self._now()
        self.latest_run.status = "completed"
        self.latest_run.failure_reason = ""
        return self.latest_run

    def fail_run(self, reason: str) -> RunState:
        self.latest_run.final_response_text = "".join(self.latest_run.streamed_output_accumulator)
        self.latest_run.completed_at = self._now()
        self.latest_run.status = "failed"
        self.latest_run.failure_reason = reason
        return self.latest_run

    def set_idle(self) -> None:
        self.latest_run.status = "idle"

    def begin_index_build(self) -> None:
        self.index_state = IndexState(latest_index=None, status="building", failure_reason="")

    def complete_index_build(self, architecture_index: ArchitectureIndex) -> ArchitectureIndex:
        architecture_index.status = "completed"
        self.index_state = IndexState(latest_index=architecture_index, status="completed", failure_reason="")
        return architecture_index

    def fail_index_build(self, reason: str) -> None:
        self.index_state.status = "failed"
        self.index_state.failure_reason = reason

    def begin_selection(self) -> None:
        self.selection_state = SelectionState(latest_selection=None, status="selecting", failure_reason="")

    def complete_selection(self, selection_result: SelectionResult) -> SelectionResult:
        self.selection_state = SelectionState(latest_selection=selection_result, status="completed", failure_reason="")
        return selection_result

    def fail_selection(self, reason: str) -> None:
        self.selection_state.status = "failed"
        self.selection_state.failure_reason = reason

    def begin_bundle_build(self) -> None:
        self.bundle_state = BundleState(latest_bundle=None, status="building", failure_reason="")

    def complete_bundle_build(self, bundle: WorkingSetBundle) -> WorkingSetBundle:
        self.bundle_state = BundleState(latest_bundle=bundle, status="completed", failure_reason="")
        return bundle

    def fail_bundle_build(self, reason: str) -> None:
        self.bundle_state.status = "failed"
        self.bundle_state.failure_reason = reason

    def set_queue_state(self, spec_queue: SpecQueueState, status: str = "idle", failure_reason: str = "") -> None:
        self.queue_runtime = QueueRuntimeState(spec_queue=spec_queue, status=status, failure_reason=failure_reason)

    def set_restore_preview(self, preview: RestorePreview) -> None:
        self.restore_state.latest_preview = preview

    def begin_restore(self) -> None:
        self.restore_state.latest_restore = None
        self.restore_state.status = "restoring"
        self.restore_state.failure_reason = ""

    def complete_restore(self, restore_result: RestoreResult) -> RestoreResult:
        self.restore_state.latest_restore = restore_result
        self.restore_state.status = restore_result.status
        self.restore_state.failure_reason = ""
        return restore_result

    def fail_restore(self, reason: str) -> None:
        self.restore_state.status = "failed"
        self.restore_state.failure_reason = reason

    def begin_bundle_edit(self, edit_run: BundleEditRun) -> None:
        self.bundle_edit_state = BundleEditState(latest_edit_run=edit_run, status="running", failure_reason="")

    def complete_bundle_edit(self, edit_run: BundleEditRun) -> None:
        self.bundle_edit_state = BundleEditState(latest_edit_run=edit_run, status="completed", failure_reason="")

    def fail_bundle_edit(self, edit_run: BundleEditRun, reason: str) -> None:
        self.bundle_edit_state = BundleEditState(latest_edit_run=edit_run, status="failed", failure_reason=reason)

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from .models import SessionState, SessionMemoryEntry, MemoryEntryType, WorkingSet
from .working_set_manager import WorkingSetManager
from .eviction import SessionEvictor

class SessionUpdater:
    def __init__(self, working_set_manager: WorkingSetManager, evictor: Optional[SessionEvictor] = None):
        self.working_set_manager = working_set_manager
        self.evictor = evictor or SessionEvictor()

    def record_translation_event(self, session: SessionState, draft_id: str, request_text: str, inferred_files: List[str], template_id: Optional[str]):
        entry = SessionMemoryEntry(
            entry_id=f"mem_{uuid.uuid4().hex[:8]}",
            entry_type=MemoryEntryType.FOCUS_UPDATE,
            timestamp=datetime.now().isoformat(),
            data={
                "request_summary": request_text[:100],
                "inferred_files": inferred_files,
                "template_id": template_id
            },
            source_draft_id=draft_id
        )
        session.memory_entries.append(entry)
        session.recent_draft_ids.insert(0, draft_id)
        session.recent_draft_ids = session.recent_draft_ids[:10]

        if template_id:
            template_entry = SessionMemoryEntry(
                entry_id=f"mem_{uuid.uuid4().hex[:8]}",
                entry_type=MemoryEntryType.TEMPLATE_USED,
                timestamp=datetime.now().isoformat(),
                data={"template_id": template_id},
                source_draft_id=draft_id
            )
            session.memory_entries.append(template_entry)

        self.working_set_manager.update_primary_files(session.working_set, inferred_files, "translation_inference", draft_id)
        self.evictor.prune_memory_entries(session)
        self._update_focus_summary(session)

    def record_compile_event(self, session: SessionState, draft_id: str, plan_id: str, success: bool, errors: List[str]):
        entry_type = MemoryEntryType.COMPILE_SUCCESS if success else MemoryEntryType.COMPILE_FAILURE
        entry = SessionMemoryEntry(
            entry_id=f"mem_{uuid.uuid4().hex[:8]}",
            entry_type=entry_type,
            timestamp=datetime.now().isoformat(),
            data={
                "plan_id": plan_id,
                "error_count": len(errors),
                "errors": errors[:5]
            },
            source_draft_id=draft_id
        )
        session.memory_entries.append(entry)
        if success:
            session.recent_compiled_plan_ids.insert(0, plan_id)
            session.recent_compiled_plan_ids = session.recent_compiled_plan_ids[:10]

        self.evictor.prune_memory_entries(session)
        self._update_focus_summary(session)

    def record_execution_event(self, session: SessionState, run_id: str, success: bool, modified_files: List[str], failed_tests: List[str]):
        entry_type = MemoryEntryType.RUN_SUCCESS if success else MemoryEntryType.RUN_FAILURE
        entry = SessionMemoryEntry(
            entry_id=f"mem_{uuid.uuid4().hex[:8]}",
            entry_type=entry_type,
            timestamp=datetime.now().isoformat(),
            data={
                "modified_files": modified_files,
                "failed_tests": failed_tests
            },
            source_run_id=run_id
        )
        session.memory_entries.append(entry)
        session.recent_run_ids.insert(0, run_id)
        session.recent_run_ids = session.recent_run_ids[:10]

        if modified_files:
            self.working_set_manager.update_primary_files(session.working_set, modified_files, "execution_mutation", run_id)

        if failed_tests:
            self.working_set_manager.update_failure_files(session.working_set, failed_tests, "test_failure")

        self.evictor.prune_memory_entries(session)
        self._update_focus_summary(session)

    def record_restore_event(self, session: SessionState, restore_id: str, baseline_run_id: str):
        entry = SessionMemoryEntry(
            entry_id=f"mem_{uuid.uuid4().hex[:8]}",
            entry_type=MemoryEntryType.RESTORE_EVENT,
            timestamp=datetime.now().isoformat(),
            data={"baseline_run_id": baseline_run_id},
            source_restore_id=restore_id
        )
        session.memory_entries.append(entry)
        session.recent_restore_ids.insert(0, restore_id)

        # Degrade confidence
        session.working_set.confidence *= 0.8
        self._update_focus_summary(session)

    def _update_focus_summary(self, session: SessionState):
        recent_files = ", ".join(session.working_set.primary_files[:3])
        last_event = session.memory_entries[-1].entry_type.value if session.memory_entries else "none"

        summary = f"Focus: {recent_files if recent_files else 'None'}. Last Event: {last_event}."
        session.current_focus_summary = summary

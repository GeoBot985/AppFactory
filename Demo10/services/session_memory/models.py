from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid

class MemoryEntryType(Enum):
    FOCUS_UPDATE = "focus_update"
    TARGET_FILE_UPDATE = "target_file_update"
    SYMBOL_UPDATE = "symbol_update"
    COMPILE_SUCCESS = "compile_success"
    COMPILE_FAILURE = "compile_failure"
    RUN_SUCCESS = "run_success"
    RUN_FAILURE = "run_failure"
    TEST_FAILURE = "test_failure"
    RESTORE_EVENT = "restore_event"
    APPROVAL_REJECTION = "approval_rejection"
    TEMPLATE_USED = "template_used"

@dataclass
class SessionMemoryEntry:
    entry_id: str
    entry_type: MemoryEntryType
    timestamp: str
    data: Dict[str, Any] = field(default_factory=dict)
    source_run_id: Optional[str] = None
    source_task_id: Optional[str] = None
    source_draft_id: Optional[str] = None
    source_restore_id: Optional[str] = None

@dataclass
class WorkingSet:
    working_set_id: str
    primary_files: List[str] = field(default_factory=list)
    secondary_files: List[str] = field(default_factory=list)
    recent_symbols: List[str] = field(default_factory=list)
    recent_failure_files: List[str] = field(default_factory=list)
    recent_test_files: List[str] = field(default_factory=list)
    last_entrypoint_files: List[str] = field(default_factory=list)
    selection_reasons: Dict[str, str] = field(default_factory=dict)
    source_run_ids: List[str] = field(default_factory=list)
    confidence: float = 1.0 # 0.0 to 1.0

@dataclass
class SessionState:
    session_id: str
    workspace_root: str
    created_at: str
    updated_at: str
    status: str = "active" # active, inactive, archived
    active_request_id: Optional[str] = None
    current_focus_summary: str = ""
    working_set: WorkingSet = field(default_factory=lambda: WorkingSet(working_set_id=f"ws_{uuid.uuid4().hex[:8]}"))
    memory_entries: List[SessionMemoryEntry] = field(default_factory=list)
    recent_draft_ids: List[str] = field(default_factory=list)
    recent_compiled_plan_ids: List[str] = field(default_factory=list)
    recent_run_ids: List[str] = field(default_factory=list)
    recent_restore_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "workspace_root": self.workspace_root,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "active_request_id": self.active_request_id,
            "current_focus_summary": self.current_focus_summary,
            "working_set": {
                "working_set_id": self.working_set.working_set_id,
                "primary_files": self.working_set.primary_files,
                "secondary_files": self.working_set.secondary_files,
                "recent_symbols": self.working_set.recent_symbols,
                "recent_failure_files": self.working_set.recent_failure_files,
                "recent_test_files": self.working_set.recent_test_files,
                "last_entrypoint_files": self.working_set.last_entrypoint_files,
                "selection_reasons": self.working_set.selection_reasons,
                "source_run_ids": self.working_set.source_run_ids,
                "confidence": self.working_set.confidence
            },
            "memory_entries": [
                {
                    "entry_id": e.entry_id,
                    "entry_type": e.entry_type.value,
                    "timestamp": e.timestamp,
                    "data": e.data,
                    "source_run_id": e.source_run_id,
                    "source_task_id": e.source_task_id,
                    "source_draft_id": e.source_draft_id,
                    "source_restore_id": e.source_restore_id
                } for e in self.memory_entries
            ],
            "recent_draft_ids": self.recent_draft_ids,
            "recent_compiled_plan_ids": self.recent_compiled_plan_ids,
            "recent_run_ids": self.recent_run_ids,
            "recent_restore_ids": self.recent_restore_ids
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SessionState:
        ws_data = data.get("working_set", {})
        working_set = WorkingSet(
            working_set_id=ws_data.get("working_set_id", f"ws_{uuid.uuid4().hex[:8]}"),
            primary_files=ws_data.get("primary_files", []),
            secondary_files=ws_data.get("secondary_files", []),
            recent_symbols=ws_data.get("recent_symbols", []),
            recent_failure_files=ws_data.get("recent_failure_files", []),
            recent_test_files=ws_data.get("recent_test_files", []),
            last_entrypoint_files=ws_data.get("last_entrypoint_files", []),
            selection_reasons=ws_data.get("selection_reasons", {}),
            source_run_ids=ws_data.get("source_run_ids", []),
            confidence=ws_data.get("confidence", 1.0)
        )

        entries = []
        for e in data.get("memory_entries", []):
            entries.append(SessionMemoryEntry(
                entry_id=e["entry_id"],
                entry_type=MemoryEntryType(e["entry_type"]),
                timestamp=e["timestamp"],
                data=e.get("data", {}),
                source_run_id=e.get("source_run_id"),
                source_task_id=e.get("source_task_id"),
                source_draft_id=e.get("source_draft_id"),
                source_restore_id=e.get("source_restore_id")
            ))

        return cls(
            session_id=data["session_id"],
            workspace_root=data["workspace_root"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            status=data.get("status", "active"),
            active_request_id=data.get("active_request_id"),
            current_focus_summary=data.get("current_focus_summary", ""),
            working_set=working_set,
            memory_entries=entries,
            recent_draft_ids=data.get("recent_draft_ids", []),
            recent_compiled_plan_ids=data.get("recent_compiled_plan_ids", []),
            recent_run_ids=data.get("recent_run_ids", []),
            recent_restore_ids=data.get("recent_restore_ids", [])
        )

from __future__ import annotations
from typing import Dict, Any, List
from .models import SessionState

class SessionContextAdapter:
    def __init__(self, session: SessionState):
        self.session = session

    def get_context_for_translation(self) -> Dict[str, Any]:
        return {
            "current_focus_summary": self.session.current_focus_summary,
            "recent_primary_files": self.session.working_set.primary_files,
            "recent_failure_files": self.session.working_set.recent_failure_files,
            "last_template_id": self._get_last_template_id(),
            "working_set_confidence": self.session.working_set.confidence
        }

    def get_context_for_targeting(self) -> Dict[str, Any]:
        return {
            "primary_files": self.session.working_set.primary_files,
            "recent_symbols": self.session.working_set.recent_symbols,
            "failure_files": self.session.working_set.recent_failure_files,
            "confidence": self.session.working_set.confidence
        }

    def get_context_for_repair(self) -> Dict[str, Any]:
        return {
            "recent_compile_errors": self._get_recent_compile_errors(),
            "recent_failures": self.session.working_set.recent_failure_files,
            "last_template_id": self._get_last_template_id()
        }

    def _get_last_template_id(self) -> str | None:
        for entry in reversed(self.session.memory_entries):
            if entry.entry_type.value == "template_used":
                return entry.data.get("template_id")
        return None

    def _get_recent_compile_errors(self) -> List[str]:
        errors = []
        for entry in reversed(self.session.memory_entries):
            if entry.entry_type.value == "compile_failure":
                errors.extend(entry.data.get("errors", []))
                if len(errors) >= 5:
                    break
        return errors[:5]

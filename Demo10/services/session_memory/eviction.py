from __future__ import annotations
from typing import List
from .models import SessionState, SessionMemoryEntry

class SessionEvictor:
    def __init__(self, max_entries: int = 50):
        self.max_entries = max_entries

    def prune_memory_entries(self, session: SessionState):
        if len(session.memory_entries) > self.max_entries:
            # Deterministic eviction: keep newest entries
            session.memory_entries = session.memory_entries[-self.max_entries:]

    def degrade_stale_confidence(self, session: SessionState, decay_factor: float = 0.95):
        # Could be called on new requests to slightly decay confidence of old working set
        session.working_set.confidence *= decay_factor
        if session.working_set.confidence < 0.1:
             session.working_set.confidence = 0.1

from __future__ import annotations
from typing import List, Dict, Set
from .models import WorkingSet

class WorkingSetManager:
    def __init__(self, max_primary: int = 5, max_secondary: int = 10, max_symbols: int = 20):
        self.max_primary = max_primary
        self.max_secondary = max_secondary
        self.max_symbols = max_symbols

    def update_primary_files(self, working_set: WorkingSet, files: List[str], reason: str, source_id: str):
        for f in files:
            if f in working_set.primary_files:
                working_set.primary_files.remove(f)
            working_set.primary_files.insert(0, f)
            working_set.selection_reasons[f] = reason
            if source_id not in working_set.source_run_ids:
                working_set.source_run_ids.insert(0, source_id)

        # Evict
        working_set.primary_files = working_set.primary_files[:self.max_primary]
        working_set.source_run_ids = working_set.source_run_ids[:10]

    def update_failure_files(self, working_set: WorkingSet, files: List[str], reason: str):
        for f in files:
            if f in working_set.recent_failure_files:
                working_set.recent_failure_files.remove(f)
            working_set.recent_failure_files.insert(0, f)
            working_set.selection_reasons[f] = reason

        working_set.recent_failure_files = working_set.recent_failure_files[:5]

    def update_symbols(self, working_set: WorkingSet, symbols: List[str]):
        for s in symbols:
            if s in working_set.recent_symbols:
                working_set.recent_symbols.remove(s)
            working_set.recent_symbols.insert(0, s)

        working_set.recent_symbols = working_set.recent_symbols[:self.max_symbols]

    def clear(self, working_set: WorkingSet):
        working_set.primary_files = []
        working_set.secondary_files = []
        working_set.recent_symbols = []
        working_set.recent_failure_files = []
        working_set.recent_test_files = []
        working_set.last_entrypoint_files = []
        working_set.selection_reasons = {}
        working_set.source_run_ids = []
        working_set.confidence = 1.0

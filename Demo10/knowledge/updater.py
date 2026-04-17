from pathlib import Path
from datetime import datetime
from typing import Literal
from .models import KnowledgeEntry, PatternSolution, SolutionCandidate, KnowledgeOutcome
from .store import KnowledgeStore

class KnowledgeUpdater:
    def __init__(self, workspace_root: Path):
        self.store = KnowledgeStore(workspace_root)

    def record_outcome(
        self,
        signature_id: str,
        suggestion_id: str,
        outcome: KnowledgeOutcome,
        root_cause_id: str
    ):
        kb = self.store.load_kb()

        # 1. Update or create KnowledgeEntry
        existing_entry = next(
            (e for e in kb.entries if e.signature_id == signature_id and e.suggestion_id == suggestion_id),
            None
        )

        if existing_entry:
            existing_entry.usage_count += 1
            if outcome == "resolved":
                existing_entry.success_count += 1
            existing_entry.outcome = outcome
            existing_entry.last_used = datetime.now()
        else:
            new_entry = KnowledgeEntry(
                signature_id=signature_id,
                suggestion_id=suggestion_id,
                root_cause_id=root_cause_id,
                outcome=outcome,
                usage_count=1,
                success_count=1 if outcome == "resolved" else 0,
                last_used=datetime.now()
            )
            kb.entries.append(new_entry)

        # 2. Update PatternSolution mappings
        self._update_mapping(kb, signature_id, root_cause_id)

        self.store.save_kb(kb)

    def _update_mapping(self, kb, signature_id: str, root_cause_id: str):
        # Find all entries for this signature
        signature_entries = [e for e in kb.entries if e.signature_id == signature_id]

        # Group by suggestion_id and calculate success rates
        suggestion_stats = {}
        for e in signature_entries:
            if e.suggestion_id not in suggestion_stats:
                suggestion_stats[e.suggestion_id] = {"usage": 0, "success": 0}
            suggestion_stats[e.suggestion_id]["usage"] += e.usage_count
            suggestion_stats[e.suggestion_id]["success"] += e.success_count

        candidates = []
        for sug_id, stats in suggestion_stats.items():
            candidates.append(SolutionCandidate(
                suggestion_id=sug_id,
                success_rate=stats["success"] / max(stats["usage"], 1),
                usage_count=stats["usage"],
                deterministic_rank=0 # Will be set by ranker
            ))

        # Deterministic Ranking
        # 1. success_rate desc
        # 2. usage_count desc
        # 3. suggestion_id asc
        candidates.sort(key=lambda c: (-c.success_rate, -c.usage_count, c.suggestion_id))

        for i, cand in enumerate(candidates):
            cand.deterministic_rank = i + 1

        kb.mappings[signature_id] = PatternSolution(
            signature_id=signature_id,
            root_cause_id=root_cause_id,
            ranked_solutions=candidates
        )

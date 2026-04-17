from pathlib import Path
from typing import List, Optional
from .models import PatternSolution, SolutionCandidate
from .store import KnowledgeStore

class KnowledgeQuery:
    def __init__(self, workspace_root: Path):
        self.store = KnowledgeStore(workspace_root)

    def get_solutions(self, signature_id: str) -> List[SolutionCandidate]:
        kb = self.store.load_kb()
        mapping = kb.mappings.get(signature_id)
        if mapping:
            return mapping.ranked_solutions
        return []

    def get_top_patterns(self, limit: int = 10) -> List[PatternSolution]:
        kb = self.store.load_kb()
        # Sort patterns by total usage across all solutions
        patterns = list(kb.mappings.values())
        patterns.sort(key=lambda p: sum(s.usage_count for s in p.ranked_solutions), reverse=True)
        return patterns[:limit]

    def get_successful_fixes(self, root_cause_id: str) -> List[SolutionCandidate]:
        kb = self.store.load_kb()
        # Find all solutions across all signatures for this root cause
        solutions_map = {}
        for mapping in kb.mappings.values():
            if mapping.root_cause_id == root_cause_id:
                for sol in mapping.ranked_solutions:
                    if sol.suggestion_id not in solutions_map:
                        solutions_map[sol.suggestion_id] = {"usage": 0, "success": 0}
                    # We need to aggregate success counts from entries because SolutionCandidate only has success_rate
                    pass

        # Better: iterate through entries
        agg_stats = {}
        for entry in kb.entries:
            if entry.root_cause_id == root_cause_id:
                if entry.suggestion_id not in agg_stats:
                    agg_stats[entry.suggestion_id] = {"usage": 0, "success": 0}
                agg_stats[entry.suggestion_id]["usage"] += entry.usage_count
                agg_stats[entry.suggestion_id]["success"] += entry.success_count

        results = []
        for sug_id, stats in agg_stats.items():
            results.append(SolutionCandidate(
                suggestion_id=sug_id,
                success_rate=stats["success"] / max(stats["usage"], 1),
                usage_count=stats["usage"],
                deterministic_rank=0
            ))

        results.sort(key=lambda c: (-c.success_rate, -c.usage_count, c.suggestion_id))
        for i, res in enumerate(results):
            res.deterministic_rank = i + 1

        return results

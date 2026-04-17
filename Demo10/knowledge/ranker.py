from typing import List
from .models import SolutionCandidate

def rank_kb_solutions(candidates: List[SolutionCandidate]) -> List[SolutionCandidate]:
    """
    Ranks KB solutions deterministically:
    1. highest success_rate
    2. highest usage_count
    3. suggestion_id fallback
    """
    return sorted(
        candidates,
        key=lambda c: (-c.success_rate, -c.usage_count, c.suggestion_id)
    )

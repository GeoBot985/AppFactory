from typing import List
from .models import RepairSuggestion

def rank_suggestions(suggestions: List[RepairSuggestion]) -> List[RepairSuggestion]:
    """
    Ranks suggestions deterministically:
    1. high confidence first
    2. fewer actions first
    3. deterministic ID fallback
    """
    confidence_map = {
        "high": 0,
        "medium": 1,
        "low": 2
    }

    return sorted(
        suggestions,
        key=lambda s: (
            confidence_map.get(s.confidence, 3),
            len(s.actions),
            s.suggestion_id
        )
    )

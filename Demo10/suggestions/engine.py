from __future__ import annotations
import copy
from pathlib import Path
from typing import List, Optional, Dict, Any
from .models import RepairSuggestion, SuggestedAction
from .mappings import get_mapping
from .ranking import rank_suggestions
from .context import enrich_suggestion
from .tracking import SuggestionTracker
from Demo10.diagnostics.models import RootCause
from Demo10.services.input_compiler.repair_models import RepairAction
from Demo10.knowledge.query import KnowledgeQuery

class SuggestionEngine:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.tracker = SuggestionTracker(workspace_root)
        self.kb_query = KnowledgeQuery(workspace_root)

    def generate_suggestions(self, root_cause: RootCause, context_data: Optional[Dict[str, Any]] = None, signature_id: Optional[str] = None) -> List[RepairSuggestion]:
        """Generates and ranks suggestions for a given root cause."""
        templates = get_mapping(root_cause.root_cause_id)

        # Deep copy to avoid mutating templates
        suggestions = [copy.deepcopy(s) for s in templates]

        # Enrich suggestions with context
        for sug in suggestions:
            enrich_suggestion(sug, self.workspace_root, context_data)

        # Enrich with KB if signature_id is provided
        kb_solutions = []
        if signature_id:
            kb_solutions = self.kb_query.get_solutions(signature_id)

        # If no signature_id but we have root_cause, we can get general successful fixes
        if not kb_solutions:
            kb_solutions = self.kb_query.get_successful_fixes(root_cause.root_cause_id)

        # Update confidence and rankings based on KB
        if kb_solutions:
            kb_map = {sol.suggestion_id: sol for sol in kb_solutions}
            for sug in suggestions:
                if sug.suggestion_id in kb_map:
                    sol = kb_map[sug.suggestion_id]
                    # Confidence adjustment
                    if sol.success_rate > 0.8 and sol.usage_count > 2:
                        sug.confidence = "high"
                    elif sol.success_rate > 0.5:
                        sug.confidence = "medium"
                    else:
                        sug.confidence = "low"

                    # Store success rate in a temporary attribute for ranking if needed
                    # or just rely on confidence adjustment for rank_suggestions
                    setattr(sug, "_kb_success_rate", sol.success_rate)
                else:
                    setattr(sug, "_kb_success_rate", 0.0)
        else:
            for sug in suggestions:
                setattr(sug, "_kb_success_rate", 0.0)

        # Rank suggestions (modified to account for KB)
        def custom_rank(s: RepairSuggestion):
            confidence_map = {"high": 0, "medium": 1, "low": 2}
            return (
                confidence_map.get(s.confidence, 3),
                -getattr(s, "_kb_success_rate", 0.0), # Higher success rate first
                len(s.actions),
                s.suggestion_id
            )

        ranked = sorted(suggestions, key=custom_rank)

        return ranked

    def suggestion_to_repair_action(self, suggestion: RepairSuggestion) -> List[RepairAction]:
        """Converts a RepairSuggestion into one or more RepairActions for the Spec 042 loop."""
        repair_actions = []

        # Map categories to issue codes for RepairAction
        issue_code_map = {
            "input_fix": "INPUT_ISSUE",
            "execution_fix": "EXECUTION_ISSUE",
            "plan_fix": "PLAN_ISSUE",
            "environment_fix": "ENVIRONMENT_ISSUE",
            "retry_tuning": "RETRY_ISSUE"
        }

        issue_code = issue_code_map.get(suggestion.category, "GENERAL_ISSUE")

        for action in suggestion.actions:
            # Map SuggestedAction to RepairAction
            action_type_map = {
                "set_field": "set_field",
                "add_missing_value": "add_missing_field",
                "select_candidate": "select_from_candidates",
            }

            ra_type = action_type_map.get(action.action_type)
            if not ra_type:
                # Some suggested actions might not be directly automatable via RepairEngine yet
                continue

            repair_actions.append(RepairAction(
                action_id=f"ract_{suggestion.suggestion_id[:4]}_{len(repair_actions)}",
                issue_code=issue_code,
                action_type=ra_type, # type: ignore
                target_field=action.target_field or "",
                value=action.value,
                candidates=[], # Could be populated from context enrichment
                requires_user_input=True,
                description=action.instructions
            ))

        return repair_actions

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

class SuggestionEngine:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.tracker = SuggestionTracker(workspace_root)

    def generate_suggestions(self, root_cause: RootCause, context_data: Optional[Dict[str, Any]] = None) -> List[RepairSuggestion]:
        """Generates and ranks suggestions for a given root cause."""
        templates = get_mapping(root_cause.root_cause_id)

        # Deep copy to avoid mutating templates
        suggestions = [copy.deepcopy(s) for s in templates]

        # Enrich suggestions with context
        for sug in suggestions:
            enrich_suggestion(sug, self.workspace_root, context_data)

        # Rank suggestions
        ranked = rank_suggestions(suggestions)

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

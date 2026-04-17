from __future__ import annotations
import uuid
from typing import List, Optional, Dict, Any
from .issues import (
    CompileIssue, AMBIGUOUS_TARGET_FILE, MISSING_REQUIRED_TARGET,
    CONFLICTING_ACTIONS, NO_SUPPORTED_OPERATION
)
from .repair_models import RepairAction

class RepairMapper:
    def map_issue_to_actions(self, issue: CompileIssue, context_data: Optional[Dict[str, Any]] = None) -> List[RepairAction]:
        actions = []

        if issue.code == AMBIGUOUS_TARGET_FILE:
            # Expecting candidates in context_data or derived from message
            candidates = []
            if context_data and "candidates" in context_data:
                candidates = context_data["candidates"]

            actions.append(RepairAction(
                action_id=f"ract_{uuid.uuid4().hex[:6]}",
                issue_code=issue.code,
                action_type="select_from_candidates",
                target_field=issue.field or "operation.target",
                candidates=candidates,
                requires_user_input=True,
                description=f"Select the correct target for {issue.field}"
            ))

        elif issue.code == MISSING_REQUIRED_TARGET:
            actions.append(RepairAction(
                action_id=f"ract_{uuid.uuid4().hex[:6]}",
                issue_code=issue.code,
                action_type="add_missing_field",
                target_field=issue.field or "operation.target",
                requires_user_input=True,
                description=f"Provide a target path for {issue.field}"
            ))

        elif issue.code == CONFLICTING_ACTIONS:
            # Often involves removing one of the operations
            actions.append(RepairAction(
                action_id=f"ract_{uuid.uuid4().hex[:6]}",
                issue_code=issue.code,
                action_type="remove_operation",
                target_field=issue.field or "operations",
                requires_user_input=True,
                description="Resolve conflict by removing one of the operations"
            ))

        elif issue.code == NO_SUPPORTED_OPERATION:
            actions.append(RepairAction(
                action_id=f"ract_{uuid.uuid4().hex[:6]}",
                issue_code=issue.code,
                action_type="replace_operation",
                target_field="operations",
                candidates=["modify_file", "analyze_codebase", "review_output", "create_file"],
                requires_user_input=True,
                description="Replace unsupported operation with a valid one"
            ))

        return actions

    def annotate_issue(self, issue: CompileIssue):
        """Deterministically decides if an issue is repairable and what its type is."""
        repairable_codes = {
            AMBIGUOUS_TARGET_FILE: "select_option",
            MISSING_REQUIRED_TARGET: "provide_value",
            CONFLICTING_ACTIONS: "remove_conflict",
            NO_SUPPORTED_OPERATION: "provide_value"
        }

        if issue.code in repairable_codes:
            issue.repairable = True
            issue.repair_type = repairable_codes[issue.code]

from typing import Dict, List
from .models import RepairSuggestion, SuggestedAction

SUGGESTION_MAPPINGS: Dict[str, List[RepairSuggestion]] = {
    "input_error.missing_target": [
        RepairSuggestion(
            suggestion_id="sug_input_missing_target",
            root_cause_id="input_error.missing_target",
            category="input_fix",
            description="Add the missing target file or directory.",
            confidence="high",
            actions=[
                SuggestedAction(
                    action_type="add_missing_value",
                    target_field="operation.target",
                    instructions="Specify the target path for this operation."
                )
            ]
        )
    ],
    "input_error.unsupported_operation": [
        RepairSuggestion(
            suggestion_id="sug_input_unsupported_op",
            root_cause_id="input_error.unsupported_operation",
            category="input_fix",
            description="The requested operation is not supported. Map it to a valid operation type.",
            confidence="high",
            actions=[
                SuggestedAction(
                    action_type="set_field",
                    target_field="operation.op_type",
                    instructions="Select a supported operation type from: modify_file, create_file, analyze_codebase, review_output."
                )
            ]
        )
    ],
    "plan_error.dependency_cycle": [
        RepairSuggestion(
            suggestion_id="sug_plan_dep_cycle",
            root_cause_id="plan_error.dependency_cycle",
            category="plan_fix",
            description="A dependency cycle was detected in the plan.",
            confidence="medium",
            actions=[
                SuggestedAction(
                    action_type="rerun_with_context",
                    instructions="Remove the conflicting operation or reorder instructions to break the cycle."
                )
            ]
        )
    ],
    "execution_error.invalid_path": [
        RepairSuggestion(
            suggestion_id="sug_exec_invalid_path",
            root_cause_id="execution_error.invalid_path",
            category="execution_fix",
            description="The specified path is invalid or outside the workspace.",
            confidence="high",
            actions=[
                SuggestedAction(
                    action_type="verify_path",
                    instructions="Verify that the path exists within the workspace."
                )
            ]
        )
    ],
    "execution_error.permission": [
        RepairSuggestion(
            suggestion_id="sug_exec_permission",
            root_cause_id="execution_error.permission",
            category="environment_fix",
            description="Permission denied when accessing file or directory.",
            confidence="medium",
            actions=[
                SuggestedAction(
                    action_type="inspect_artifact",
                    instructions="Check file permissions and ensure the process has necessary access."
                )
            ]
        )
    ],
    "transient_error.exhausted": [
        RepairSuggestion(
            suggestion_id="sug_transient_exhausted",
            root_cause_id="transient_error.exhausted",
            category="retry_tuning",
            description="Retry policy exhausted after multiple failures.",
            confidence="medium",
            actions=[
                SuggestedAction(
                    action_type="adjust_parameter",
                    target_field="retry_count",
                    value="3",
                    instructions="Increase retry count or delay, and inspect underlying command for persistent issues."
                )
            ]
        )
    ],
    "environment_error.missing_dependency": [
        RepairSuggestion(
            suggestion_id="sug_env_missing_dep",
            root_cause_id="environment_error.missing_dependency",
            category="environment_fix",
            description="A required system dependency or executable is missing.",
            confidence="high",
            actions=[
                SuggestedAction(
                    action_type="install_dependency",
                    instructions="Install the required tool and ensure it is in the system PATH."
                )
            ]
        )
    ],
    "rollback_error.snapshot_missing": [
        RepairSuggestion(
            suggestion_id="sug_rollback_snapshot_missing",
            root_cause_id="rollback_error.snapshot_missing",
            category="rollback_fix",
            description="Required snapshot for rollback is missing.",
            confidence="medium",
            actions=[
                SuggestedAction(
                    action_type="inspect_artifact",
                    instructions="Enable snapshot capture and verify snapshot storage path."
                )
            ]
        )
    ],
    "verification_error.drift": [
        RepairSuggestion(
            suggestion_id="sug_verif_drift",
            root_cause_id="verification_error.drift",
            category="verification_fix",
            description="Execution drift detected during verification against golden run.",
            confidence="medium",
            actions=[
                SuggestedAction(
                    action_type="inspect_artifact",
                    instructions="Inspect output differences and manually re-baseline if changes are expected."
                )
            ]
        )
    ],
    "policy_error.policy_violation": [
        RepairSuggestion(
            suggestion_id="sug_policy_violation",
            root_cause_id="policy_error.policy_violation",
            category="policy_fix",
            description="Promotion rejected due to policy violations.",
            confidence="medium",
            actions=[
                SuggestedAction(
                    action_type="rerun_with_context",
                    instructions="Review failed verification cases and resolve drift or failures before re-promoting."
                )
            ]
        )
    ]
}

def get_mapping(root_cause_id: str) -> List[RepairSuggestion]:
    return SUGGESTION_MAPPINGS.get(root_cause_id, [])

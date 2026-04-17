from typing import Dict, Any
from telemetry.models import TelemetryEvent
from .models import RootCause, RootCauseCategory

CLASSIFICATION_RULES = {
    # Input Errors
    "MISSING_REQUIRED_TARGET": ("input_error", "missing_target", "Required target is missing from input"),
    "NO_SUPPORTED_OPERATION": ("input_error", "unsupported_operation", "Requested operation is not supported"),

    # Plan Errors
    "PLAN_EXPANSION_FAILURE": ("plan_error", "expansion_failure", "Failed to expand plan from IR"),
    "DEPENDENCY_CYCLE": ("plan_error", "dependency_cycle", "Dependency cycle detected in plan"),

    # Execution Errors
    "INVALID_PATH": ("execution_error", "invalid_path", "Target path is invalid or outside workspace"),
    "FILE_ACCESS_DENIED": ("execution_error", "permission", "Permission denied when accessing file"),
    "PRECONDITION_FAILED": ("execution_error", "precondition", "Step preconditions were not met"),
    "POSTCONDITION_FAILED": ("execution_error", "postcondition", "Step postconditions were not met"),

    # Transient Errors (often from step_failed event metadata)
    "RECOVERED": ("transient_error", "recovered", "Failure was resolved via retry"),
    "EXHAUSTED": ("transient_error", "exhausted", "Retry policy exhausted for retryable failure"),

    # Environment Errors
    "MISSING_DEPENDENCY": ("environment_error", "missing_dependency", "A required system dependency or executable is missing"),
    "EXTERNAL_PATH_NOT_FOUND": ("environment_error", "external_path", "External path not found"),

    # Rollback Errors
    "SNAPSHOT_MISSING": ("rollback_error", "snapshot_missing", "Required snapshot for rollback is missing"),
    "COMPENSATION_FAILED": ("rollback_error", "compensation_failure", "Failed to execute compensation action during rollback"),

    # Verification Errors
    "DRIFT_DETECTED": ("verification_error", "drift", "Execution drift detected during verification"),
    "GOLDEN_RUN_CORRUPTED": ("verification_error", "corruption", "Golden run artifact is corrupted or invalid"),

    # Policy Errors
    "PROMOTION_REJECTED": ("policy_error", "policy_violation", "Promotion failed policy evaluation"),
}

def classify_failure(event: TelemetryEvent) -> RootCause:
    error_code = event.payload.get("error_code", "UNKNOWN_ERROR")

    # Special cases based on event context
    if event.event_type == "step_failed":
        if event.payload.get("is_terminal") and event.payload.get("classification") == "retryable":
            if event.payload.get("attempt_index", 0) >= 1: # Usually indicates exhaustion if terminal and retryable
                error_code = "EXHAUSTED"

    if event.event_type == "step_completed":
        if event.payload.get("attempts", 1) > 1:
            error_code = "RECOVERED"

    rule = CLASSIFICATION_RULES.get(error_code)

    if not rule:
        # Fallback based on error_code prefixes or patterns if needed
        if "TIMEOUT" in error_code:
            return RootCause(
                root_cause_id="transient_error.timeout",
                category="transient_error",
                subcategory="timeout",
                description=f"Operation timed out: {error_code}",
                deterministic=True
            )

        return RootCause(
            root_cause_id="execution_error.unknown",
            category="execution_error",
            subcategory="unknown",
            description=f"Unclassified error: {error_code}",
            deterministic=False
        )

    category, subcategory, description = rule
    return RootCause(
        root_cause_id=f"{category}.{subcategory}",
        category=category,
        subcategory=subcategory,
        description=description,
        deterministic=True
    )

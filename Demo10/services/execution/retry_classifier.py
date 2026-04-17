from typing import Literal, Optional

def classify_failure(
    error_code: str,
    step_type: Optional[str] = None,
    is_transient: Optional[bool] = None
) -> Literal["retryable", "terminal"]:
    # Explicit transient flag from handler takes high priority if it's EXECUTION_ERROR
    if error_code == "EXECUTION_ERROR" and is_transient is True:
        return "retryable"

    # Retryable v1 candidates
    if error_code == "COMMAND_FAILED":
        return "retryable"

    if error_code == "POSTCONDITION_FAILED":
        # validation-style steps only
        validation_steps = ["validate_output", "verify_file_exists", "analyze_code", "verify_changes"]
        if step_type in validation_steps:
            return "retryable"
        return "terminal"

    if error_code == "FILE_ACCESS_DENIED":
        # In v1, we assume it might be a temporary lock if we got this code
        return "retryable"

    if error_code == "DEPENDENCY_NOT_SATISFIED":
        # only for delayed materialization checks, not graph errors.
        # But wait, graph errors should probably not reach here if engine checks them first.
        # If it reached here, it might be a runtime dependency check.
        return "retryable"

    # Terminal v1 candidates
    terminal_codes = [
        "INVALID_PATH",
        "PRECONDITION_FAILED",
        "WORKSPACE_BOUNDARY_VIOLATION",
        "UNSUPPORTED_OPERATION",
        "MALFORMED_INPUT",
        "DETERMINISTIC_TRANSFORM_FAILURE",
        "NOT_IMPLEMENTED"
    ]
    if error_code in terminal_codes:
        return "terminal"

    # Default: terminal
    return "terminal"

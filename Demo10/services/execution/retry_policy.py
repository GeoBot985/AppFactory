from typing import Dict, Optional
from services.execution.models import RetryPolicy

DEFAULT_RETRYABLE_ERROR_CODES = [
    "COMMAND_FAILED",
    "POSTCONDITION_FAILED",
    "FILE_ACCESS_DENIED",
    "DEPENDENCY_NOT_SATISFIED",
    "EXECUTION_ERROR"
]

DEFAULT_RETRY_POLICY = RetryPolicy(
    max_attempts=2,
    retryable_error_codes=DEFAULT_RETRYABLE_ERROR_CODES,
    delay_ms=250,
    backoff_mode="fixed",
    requires_recheck=True,
)

STEP_TYPE_POLICIES: Dict[str, RetryPolicy] = {
    "read_file": RetryPolicy(
        max_attempts=2,
        retryable_error_codes=DEFAULT_RETRYABLE_ERROR_CODES,
        delay_ms=250,
        backoff_mode="fixed",
        requires_recheck=True
    ),
    "run_command": RetryPolicy(
        max_attempts=3,
        retryable_error_codes=DEFAULT_RETRYABLE_ERROR_CODES,
        delay_ms=500,
        backoff_mode="linear",
        requires_recheck=True
    ),
    "validate_output": RetryPolicy(
        max_attempts=3,
        retryable_error_codes=DEFAULT_RETRYABLE_ERROR_CODES,
        delay_ms=250,
        backoff_mode="fixed",
        requires_recheck=True
    ),
    "write_file": RetryPolicy(
        max_attempts=1,
        retryable_error_codes=[],
        delay_ms=0,
        backoff_mode="none",
        requires_recheck=False
    ),
    "modify_file": RetryPolicy(
        max_attempts=1,
        retryable_error_codes=[],
        delay_ms=0,
        backoff_mode="none",
        requires_recheck=False
    )
}

def get_retry_policy(step_type: str) -> RetryPolicy:
    return STEP_TYPE_POLICIES.get(step_type, DEFAULT_RETRY_POLICY)

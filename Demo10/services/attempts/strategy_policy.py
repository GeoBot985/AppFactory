from __future__ import annotations

from services.attempts.failure_classifier import NON_REPAIRABLE_FAILURES
from services.attempts.models import AttemptConfig, AttemptRecord


def select_next_strategy(config: AttemptConfig, history: list[AttemptRecord], failure_class: str) -> tuple[str, str]:
    if failure_class in NON_REPAIRABLE_FAILURES:
        return "abort_nonrepairable", "failure class is policy-blocked"

    attempt_count = len(history)
    if attempt_count >= config.max_total_attempts:
        return "abort_exhausted", "max attempts reached"

    if attempt_count == 1:
        if failure_class in {"python_syntax_error", "python_indentation_error", "empty_file_after_patch", "patch_target_not_found", "patch_match_count_mismatch", "operation_schema_invalid", "batch_invalid_broken_import", "batch_invalid_removed_symbol_still_referenced", "batch_invalid_duplicate_symbol", "batch_invalid_missing_symbol", "test_failure_assertion", "test_failure_exception", "import_error", "module_not_found", "runtime_error", "test_timeout", "test_execution_error"}:
            if failure_class.startswith("python") or failure_class == "empty_file_after_patch":
                if config.allow_repair_after_validation_failure:
                    return "repair_generate", "targeted repair after validation failure"
            else:
                return "repair_generate", "targeted repair after deterministic failure"
        return "repair_generate", "targeted repair default"

    previous = history[-2] if len(history) >= 2 else None
    current = history[-1]
    duplicate = bool(previous and previous.failure_fingerprint and previous.failure_fingerprint == current.failure_fingerprint)
    if attempt_count == 2:
        if duplicate and not config.allow_full_regenerate_after_patch_failure:
            return "abort_nonrepairable", "duplicate failure with regenerate disabled"
        return "full_regenerate", "escalate after repeated or second failure"

    return "abort_exhausted", "bounded attempts exhausted"


def classify_final_outcome(history: list[AttemptRecord], success: bool, stopped_reason: str) -> str:
    if success:
        if len(history) == 1:
            return "succeeded_first_try"
        if history[-1].attempt_type == "full_regenerate":
            return "succeeded_after_regenerate"
        return "succeeded_after_repair"
    if stopped_reason == "nonrepairable":
        return "failed_nonrepairable"
    if stopped_reason == "policy_blocked":
        return "failed_policy_blocked"
    return "failed_exhausted_attempts"

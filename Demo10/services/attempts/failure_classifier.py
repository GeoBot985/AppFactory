from __future__ import annotations

from services.file_ops.models import FileOperationBatchResult


NON_REPAIRABLE_FAILURES = {"path_validation_failure", "binary_file_not_supported", "policy_blocked_complex_batch"}


def classify_batch_failure(batch: FileOperationBatchResult) -> tuple[str, str]:
    if batch.validation_errors:
        first = batch.validation_errors[0].lower()
        if "outside_workspace" in first:
            return "path_validation_failure", first
        if "invalid_operation_schema" in first:
            return "operation_schema_invalid", first
        return "unknown_validation_failure", first

    if batch.batch_summary and batch.batch_summary.batch_validation_status.startswith("batch_invalid"):
        status = batch.batch_summary.batch_validation_status
        detail = batch.batch_summary.batch_failure_reasons[0] if batch.batch_summary.batch_failure_reasons else status
        if detail.startswith("policy_blocked_complex_batch"):
            return "policy_blocked_complex_batch", detail
        return status, detail

    if batch.test_summary and batch.test_summary.status == "failed":
        return batch.test_summary.failure_class or "test_execution_error", batch.test_summary.failure_detail or "tests failed"
    if batch.test_summary and batch.test_summary.no_tests_found:
        return "no_tests_found", batch.test_summary.failure_detail or "no tests detected"

    if not batch.results:
        return "unknown_validation_failure", "no mutation results"

    result = next((item for item in batch.results if item.status == "failed"), batch.results[0])
    code = result.failure_code or "unknown_validation_failure"
    validation = result.validation
    if code == "patch_target_not_found":
        return "patch_target_not_found", result.failure_reason or code
    if code == "patch_match_count_mismatch":
        return "patch_match_count_mismatch", result.failure_reason or code
    if code in {"invalid_operation_schema", "conflicting_operations"}:
        return "operation_schema_invalid", result.failure_reason or code
    if code == "binary_file_not_supported":
        return "binary_file_not_supported", result.failure_reason or code
    if code == "code_validation_failed" and validation:
        if validation.error_type == "IndentationError":
            return "python_indentation_error", validation.error_message or validation.error_type
        if validation.error_type in {"SyntaxError", "IndentationError"}:
            return "python_syntax_error", validation.error_message or validation.error_type
        if validation.error_type in {"EmptyFileError", "EmptyModuleBody"}:
            return "empty_file_after_patch", validation.error_message or validation.error_type
        return "unknown_validation_failure", validation.error_message or validation.error_type
    if code == "file_not_found":
        return "patch_target_not_found", result.failure_reason or code
    if code == "file_already_exists":
        return "operation_schema_invalid", result.failure_reason or code
    return "unknown_validation_failure", result.failure_reason or code


def classify_edit_failure(reason: str) -> tuple[str, str]:
    lowered = (reason or "").lower()
    if "anchor not found" in lowered or "no match selected" in lowered:
        return "patch_target_not_found", reason
    if "ambiguous anchor" in lowered:
        return "patch_match_count_mismatch", reason
    return "unknown_validation_failure", reason or "edit failed"


def fingerprint_failure(failure_class: str, detail: str, path: str = "", line: int = 0, column: int = 0) -> str:
    return f"{failure_class}|{path}|{line}|{column}|{detail}".strip()

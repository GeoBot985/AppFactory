from __future__ import annotations


def classify_test_failure(stdout: str, stderr: str, exit_code: int, timed_out: bool, no_tests_found: bool) -> tuple[str, str]:
    text = f"{stdout}\n{stderr}".lower()
    if timed_out:
        return "test_timeout", "test execution timed out"
    if no_tests_found:
        return "no_tests_found", "no tests detected"
    if "modulenotfounderror" in text:
        return "module_not_found", "module not found during test execution"
    if "importerror" in text:
        return "import_error", "import error during test execution"
    if any(token in text for token in ["zerodivisionerror", "typeerror", "valueerror", "attributeerror", "runtimeerror"]):
        return "runtime_error", "runtime error during tests"
    if "assert" in text or "assertionerror" in text or "failed" in text:
        return "test_failure_assertion", "assertion failure during tests"
    if "exception" in text or "traceback" in text or exit_code != 0:
        return "test_failure_exception", "exception during tests"
    return "test_execution_error", "test execution error"

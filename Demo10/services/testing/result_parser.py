from __future__ import annotations

import re


def parse_pytest_summary(stdout: str, stderr: str) -> dict:
    text = f"{stdout}\n{stderr}"
    summary = {
        "total_tests": 0,
        "tests_passed": 0,
        "tests_failed": 0,
        "tests_skipped": 0,
        "failing_tests": [],
    }
    match = re.search(r"(?P<passed>\d+)\s+passed", text)
    if match:
        summary["tests_passed"] = int(match.group("passed"))
    match = re.search(r"(?P<failed>\d+)\s+failed", text)
    if match:
        summary["tests_failed"] = int(match.group("failed"))
    match = re.search(r"(?P<skipped>\d+)\s+skipped", text)
    if match:
        summary["tests_skipped"] = int(match.group("skipped"))
    summary["total_tests"] = summary["tests_passed"] + summary["tests_failed"] + summary["tests_skipped"]
    failing = re.findall(r"FAILED\s+([^\s]+::[^\s]+)", text)
    summary["failing_tests"] = failing
    return summary


def parse_unittest_summary(stdout: str, stderr: str) -> dict:
    text = f"{stdout}\n{stderr}"
    summary = {
        "total_tests": 0,
        "tests_passed": 0,
        "tests_failed": 0,
        "tests_skipped": 0,
        "failing_tests": [],
    }
    match = re.search(r"Ran\s+(\d+)\s+tests?", text)
    if match:
        summary["total_tests"] = int(match.group(1))
    failures = re.findall(r"FAIL:\s+([^\s]+)", text)
    errors = re.findall(r"ERROR:\s+([^\s]+)", text)
    summary["failing_tests"] = failures + errors
    summary["tests_failed"] = len(summary["failing_tests"])
    summary["tests_passed"] = max(0, summary["total_tests"] - summary["tests_failed"])
    return summary

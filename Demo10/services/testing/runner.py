from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from services.testing.failure_classifier import classify_test_failure
from services.testing.result_parser import parse_pytest_summary, parse_unittest_summary


@dataclass
class TestRunResult:
    test_run_id: str
    status: str
    runner: str
    total_tests: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    exit_code: int = 0
    duration_seconds: float = 0.0
    stdout: str = ""
    stderr: str = ""
    failure_class: str = ""
    failure_detail: str = ""
    failing_tests: list[str] = field(default_factory=list)
    no_tests_found: bool = False
    timed_out: bool = False


class TestGateRunner:
    def __init__(self, max_test_duration_seconds: int = 20, no_tests_policy: str = "pass_with_warning"):
        self.max_test_duration_seconds = max_test_duration_seconds
        self.no_tests_policy = no_tests_policy

    def run(self, project_root: str | Path, simulated_files: dict[str, str | None]) -> TestRunResult:
        root = Path(project_root).expanduser().resolve()
        test_run_id = f"test_{int(time.time() * 1000)}"
        with tempfile.TemporaryDirectory(prefix="demo10_testgate_") as tmp_dir:
            tmp_root = Path(tmp_dir) / root.name
            shutil.copytree(root, tmp_root, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", ".git", ".venv", "venv", ".pytest_cache", ".mypy_cache", "node_modules", "dist", "build"))
            self._apply_overlay(tmp_root, simulated_files)
            runner = self._detect_runner(tmp_root)
            if runner == "none":
                status = "passed_with_warnings" if self.no_tests_policy == "pass_with_warning" else "failed"
                failure_class = "no_tests_found" if status != "passed_with_warnings" else ""
                return TestRunResult(
                    test_run_id=test_run_id,
                    status=status,
                    runner="none",
                    no_tests_found=True,
                    failure_class=failure_class,
                    failure_detail="no tests detected",
                )

            command = [sys.executable, "-m", "pytest", "-q"] if runner == "pytest" else [sys.executable, "-m", "unittest", "discover"]
            start = time.time()
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(tmp_root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.max_test_duration_seconds,
                )
                duration = time.time() - start
                summary = parse_pytest_summary(completed.stdout, completed.stderr) if runner == "pytest" else parse_unittest_summary(completed.stdout, completed.stderr)
                no_tests_found = False
                if runner == "pytest" and completed.returncode == 5:
                    no_tests_found = True
                elif completed.returncode == 0 and summary["total_tests"] == 0 and not summary["failing_tests"]:
                    no_tests_found = True
                if no_tests_found:
                    status = "passed_with_warnings" if self.no_tests_policy == "pass_with_warning" else "failed"
                    failure_class = "" if status == "passed_with_warnings" else "no_tests_found"
                    return TestRunResult(
                        test_run_id=test_run_id,
                        status=status,
                        runner=runner,
                        total_tests=0,
                        tests_passed=0,
                        tests_failed=0,
                        tests_skipped=0,
                        exit_code=completed.returncode,
                        duration_seconds=duration,
                        stdout=completed.stdout[:20000],
                        stderr=completed.stderr[:12000],
                        failure_class=failure_class,
                        failure_detail="no tests detected",
                        no_tests_found=True,
                    )
                status = "passed" if completed.returncode == 0 else "failed"
                failure_class = ""
                failure_detail = ""
                if completed.returncode != 0:
                    failure_class, failure_detail = classify_test_failure(completed.stdout, completed.stderr, completed.returncode, False, False)
                return TestRunResult(
                    test_run_id=test_run_id,
                    status=status,
                    runner=runner,
                    total_tests=summary["total_tests"],
                    tests_passed=summary["tests_passed"],
                    tests_failed=summary["tests_failed"],
                    tests_skipped=summary["tests_skipped"],
                    exit_code=completed.returncode,
                    duration_seconds=duration,
                    stdout=completed.stdout[:20000],
                    stderr=completed.stderr[:12000],
                    failure_class=failure_class,
                    failure_detail=failure_detail,
                    failing_tests=summary["failing_tests"],
                )
            except subprocess.TimeoutExpired as exc:
                return TestRunResult(
                    test_run_id=test_run_id,
                    status="failed",
                    runner=runner,
                    stdout=(exc.stdout or "")[:20000],
                    stderr=(exc.stderr or "")[:12000],
                    failure_class="test_timeout",
                    failure_detail="test execution timed out",
                    timed_out=True,
                    duration_seconds=self.max_test_duration_seconds,
                    exit_code=-1,
                )

    def _apply_overlay(self, tmp_root: Path, simulated_files: dict[str, str | None]) -> None:
        for rel, content in simulated_files.items():
            target = tmp_root / rel
            if content is None:
                if target.exists():
                    target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="")

    def _detect_runner(self, root: Path) -> str:
        has_tests = (root / "tests").exists() or any(root.rglob("test_*.py"))
        if not has_tests:
            return "none"
        pytest_available = subprocess.run(
            [sys.executable, "-c", "import pytest"],
            capture_output=True,
            text=True,
        )
        if pytest_available.returncode == 0:
            return "pytest"
        return "unittest"

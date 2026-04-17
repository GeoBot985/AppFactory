from pathlib import Path
from typing import List, Optional, Literal
from .golden_store import GoldenStore
from .suite_runner import SuiteRunner
from .models import VerificationResult, VerificationSuite
from .reporting import VerificationHarnessReporter

class VerificationHarness:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.golden_store = GoldenStore(workspace_root)
        self.suite_runner = SuiteRunner(workspace_root)
        self.reporter = VerificationHarnessReporter(workspace_root)

    def create_golden_run(self, source_run_id: str, notes: Optional[str] = None) -> str:
        """Blesses a source run as a Golden Run."""
        return self.golden_store.create_golden_run(source_run_id, notes)

    def create_suite(self, suite_id: str, golden_run_ids: List[str], description: str) -> VerificationSuite:
        """Creates a verification suite."""
        return self.suite_runner.create_suite(suite_id, golden_run_ids, description)

    def run_suite(self, suite_id: str, mode: Literal["strict", "tolerant"] = "strict") -> VerificationResult:
        """Runs a verification suite and produces a report."""
        result = self.suite_runner.run_verification_suite(suite_id, mode)
        self.reporter.save_verification_result(result)
        return result

    def list_golden_runs(self) -> List[str]:
        return self.golden_store.list_golden_runs()

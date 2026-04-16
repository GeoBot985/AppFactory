from __future__ import annotations
import os
import json
import time
import yaml
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from .engine import VerificationEngine
from .outcome import OutcomeSynthesizer
from .baselines import BaselineComparator
from .models import FailureStage, FinalOutcome, VerificationReport

from workspace.models import ExecutionMode, SourcePolicy, PromotionStatus
from workspace.fingerprints import FingerprintService
from workspace.snapshots import SnapshotService
from workspace.promotion import PromotionService
from workspace.conflicts import ConflictService

from services.spec_parser_service import SpecParserService
from services.task_executor_service import TaskExecutorService
from services.file_ops_service import FileOpsService
from services.ollama_service import OllamaService
from services.process_service import ProcessService
from services.audit_log_service import AuditLogService

class RegressionRunner:
    def __init__(self, project_root: Path, regression_root: Path, model_name: str = "granite4:3b"):
        self.project_root = project_root
        self.regression_root = regression_root
        self.model_name = model_name
        self.v_engine = VerificationEngine(project_root)
        self.v_synthesizer = OutcomeSynthesizer()
        self.comparator = BaselineComparator()

        self.fingerprint_service = FingerprintService()
        self.snapshot_service = SnapshotService(self.fingerprint_service)
        self.promotion_service = PromotionService(self.fingerprint_service)
        self.conflict_service = ConflictService(self.fingerprint_service)

        self.spec_parser = SpecParserService()
        self.ollama = OllamaService()
        self.process = ProcessService()
        self.audit = AuditLogService(project_root)

    def run_suite(self, suite_name: str, update_baseline: bool = False) -> Dict[str, Any]:
        suite_path = self.regression_root / suite_name
        if not suite_path.exists():
            return {"error": f"Suite {suite_name} not found"}

        results = []
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        run_log_root = self.project_root / "regression_runs" / timestamp
        run_log_root.mkdir(parents=True, exist_ok=True)

        for case_dir in sorted(suite_path.iterdir()):
            if not case_dir.is_dir(): continue

            case_result = self.run_case(case_dir, update_baseline)
            results.append(case_result)

            with open(run_log_root / f"{case_dir.name}.json", "w") as f:
                json.dump(case_result, f, indent=2)

        summary = {
            "suite": suite_name,
            "timestamp": timestamp,
            "total": len(results),
            "passed": sum(1 for r in results if r["status"] == "pass"),
            "failed": sum(1 for r in results if r["status"] == "fail"),
            "results": results
        }

        with open(run_log_root / "summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        return summary

    def run_case(self, case_dir: Path, update_baseline: bool = False) -> Dict[str, Any]:
        spec_path = case_dir / "spec.yaml"
        expected_path = case_dir / "expected_outcome.json"
        fixture_workspace = case_dir / "fixture_workspace"

        if not spec_path.exists():
            return {"case": case_dir.name, "status": "fail", "error": "spec.yaml missing"}

        with open(spec_path, "r") as f:
            spec_text = f.read()

        try:
            # 1. Parse
            tasks, verification_data = self.spec_parser.parse(spec_text)

            # 2. Setup Run Folder & Isolation (SPEC 014)
            run_folder = self.audit.create_run_folder(999) # 999 for regression

            # Use fixture if exists, else project_root
            source_ws = fixture_workspace if fixture_workspace.exists() else self.project_root

            snapshot_manifest = self.snapshot_service.create_execution_snapshot(
                run_id=run_folder.name,
                spec_id=case_dir.name,
                source_workspace=source_ws,
                execution_root=run_folder,
                mode=ExecutionMode.REGRESSION_CASE
            )
            execution_workspace = Path(snapshot_manifest.execution_workspace)

            # 3. Execute in isolated workspace
            file_ops = FileOpsService(execution_workspace)
            executor = TaskExecutorService(file_ops, self.ollama, self.process, self.model_name, run_folder=run_folder)

            failure_stage = None
            for task in tasks:
                res = executor.execute(task)
                if not res.success:
                    failure_stage = FailureStage.EDIT_FAILURE
                    break

            # 4. Verify (must use isolated path)
            v_engine = VerificationEngine(execution_workspace)
            v_report = v_engine.run(verification_data, tasks)

            # 5. Outcome Synthesis
            summary = self.v_synthesizer.synthesize(case_dir.name, tasks, v_report, failure_stage, None)

            actual_outcome = {
                "spec_id": summary.spec_id,
                "final_status": summary.final_status.value,
                "verification": summary.verification,
                "regression": summary.regression
            }

            if update_baseline:
                with open(expected_path, "w") as f:
                    json.dump(actual_outcome, f, indent=2)

                # Cleanup if success
                if execution_workspace.exists():
                    shutil.rmtree(execution_workspace)

                return {"case": case_dir.name, "status": "pass", "message": "baseline updated"}

            # Cleanup execution workspace after run (Regression cases are always hermetic/discarded)
            if execution_workspace.exists():
                shutil.rmtree(execution_workspace)

            if not expected_path.exists():
                 return {"case": case_dir.name, "status": "fail", "error": "expected_outcome.json missing"}

            with open(expected_path, "r") as f:
                expected_outcome = json.load(f)

            comparison = self.comparator.compare(actual_outcome, expected_outcome)
            return {
                "case": case_dir.name,
                "status": comparison["status"],
                "mismatches": comparison["mismatches"],
                "actual": actual_outcome
            }

        except Exception as e:
            return {"case": case_dir.name, "status": "fail", "error": str(e)}

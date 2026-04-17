import json
import uuid
import shutil
from pathlib import Path
from typing import List, Dict, Any, Literal
from datetime import datetime

from .models import VerificationSuite, VerificationResult, GoldenRunResult, VerificationReport
from .golden_store import GoldenStore
from .classifier import VerificationClassifier
from Demo10.services.replay.replay_runner import ReplayRunner
from Demo10.services.replay.models import ReplayRequest
from telemetry.events import TelemetryEmitter

class SuiteRunner:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.golden_store = GoldenStore(workspace_root)
        self.classifier = VerificationClassifier()
        self.replay_runner = ReplayRunner(workspace_root)
        self.telemetry = TelemetryEmitter(workspace_root)
        self.suites_dir = workspace_root / "runtime_data" / "verification_suites"
        self.suites_dir.mkdir(parents=True, exist_ok=True)

    def create_suite(self, suite_id: str, golden_run_ids: List[str], description: str) -> VerificationSuite:
        suite = VerificationSuite(suite_id=suite_id, golden_runs=golden_run_ids, description=description)
        suite_file = self.suites_dir / f"{suite_id}.json"
        with open(suite_file, "w") as f:
            json.dump(self._to_dict(suite), f, indent=2)
        return suite

    def load_suite(self, suite_id: str) -> VerificationSuite:
        suite_file = self.suites_dir / f"{suite_id}.json"
        if not suite_file.exists():
            raise FileNotFoundError(f"Suite {suite_id} not found")
        with open(suite_file, "r") as f:
            data = json.load(f)
        return VerificationSuite(**data)

    def run_verification_suite(self, suite_id: str, mode: Literal["strict", "tolerant"] = "strict") -> VerificationResult:
        suite = self.load_suite(suite_id)
        run_results = []

        self.telemetry.emit("verification_run", {"suite_id": suite_id, "mode": mode, "total_goldens": len(suite.golden_runs)})

        for golden_run_id in suite.golden_runs:
            print(f"Verifying Golden Run: {golden_run_id}")

            # SPEC 049 Section 8: Baseline Integrity Checks
            if not self.golden_store.verify_integrity(golden_run_id):
                run_results.append(GoldenRunResult(
                    golden_run_id=golden_run_id,
                    replay_result=None,
                    verdict="fail",
                    classification="fail",
                    drift_categories=["environment_drift"]
                ))
                print(f"GOLDEN_RUN_CORRUPTED for {golden_run_id}")
                continue

            try:
                source_run_id = self._prepare_for_replay(golden_run_id)

                request = ReplayRequest(
                    replay_id=str(uuid.uuid4())[:8],
                    source_run_id=source_run_id,
                    mode="re_execute",
                    workspace_mode="temp_workspace",
                    include_rollback=True
                )

                replay_result = self.replay_runner.run_replay(request)
                golden_result = self.classifier.classify(golden_run_id, replay_result)

                # Apply strict mode: any drift = fail
                if mode == "strict" and golden_result.classification == "warn":
                    golden_result.classification = "fail"

                run_results.append(golden_result)
                self._cleanup_after_replay(source_run_id)

            except Exception as e:
                print(f"VERIFICATION_REPLAY_FAILED for {golden_run_id}: {str(e)}")
                run_results.append(GoldenRunResult(
                    golden_run_id=golden_run_id,
                    replay_result=None,
                    verdict="fail",
                    classification="fail",
                    drift_categories=["execution_drift"]
                ))

        overall_verdict: Literal["pass", "pass_with_warnings", "fail"] = "pass"
        if any(r.classification == "fail" for r in run_results):
            overall_verdict = "fail"
        elif any(r.classification == "warn" for r in run_results):
            overall_verdict = "pass_with_warnings"

        summary = {
            "suite_id": suite_id,
            "total_runs": len(run_results),
            "pass": sum(1 for r in run_results if r.classification == "pass"),
            "warn": sum(1 for r in run_results if r.classification == "warn"),
            "fail": sum(1 for r in run_results if r.classification == "fail"),
            "timestamp": datetime.now().isoformat(),
            "mode": mode
        }

        result = VerificationResult(
            suite_id=suite_id,
            run_results=run_results,
            overall_verdict=overall_verdict,
            summary=summary
        )
        self.telemetry.emit("verification_result", {
            "suite_id": suite_id,
            "overall_verdict": overall_verdict,
            "pass": summary["pass"],
            "warn": summary["warn"],
            "fail": summary["fail"],
            "drift_events": sum(len(r.drift_categories) for r in run_results)
        })
        return result

    def _prepare_for_replay(self, golden_run_id: str) -> str:
        golden_dir = self.golden_store.golden_runs_dir / golden_run_id
        source_run_id = f"tmp_verify_{golden_run_id}"
        tmp_run_dir = self.workspace_root / "runtime_data" / "runs" / source_run_id

        if tmp_run_dir.exists():
             shutil.rmtree(tmp_run_dir)

        shutil.copytree(golden_dir / "run_artifacts", tmp_run_dir)

        with open(tmp_run_dir / "run.json", "r") as f:
            run_data = json.load(f)
            plan_id = run_data["plan_id"]

        plan_file = self.workspace_root / "runtime_data" / "execution_plans" / f"{plan_id}.json"
        if not plan_file.exists():
            plan_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(golden_dir / "plan.json", plan_file)

        with open(golden_dir / "plan.json", "r") as f:
            plan_data = json.load(f)
            ir_ref = plan_data["ir_ref"]

        ir_file = self.workspace_root / "runtime_data" / "compiler_runs" / f"{ir_ref}.json"
        if not ir_file.exists():
            ir_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(golden_dir / "ir.json", ir_file)

        return source_run_id

    def _cleanup_after_replay(self, source_run_id: str):
        tmp_run_dir = self.workspace_root / "runtime_data" / "runs" / source_run_id
        if tmp_run_dir.exists():
            shutil.rmtree(tmp_run_dir)

    def _to_dict(self, obj: Any) -> Dict[str, Any]:
        from dataclasses import asdict, is_dataclass
        if is_dataclass(obj):
            return asdict(obj)
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "__dict__"):
            return {k: self._to_dict(v) for k, v in obj.__dict__.items()}
        if isinstance(obj, list):
            return [self._to_dict(i) for i in obj]
        if isinstance(obj, dict):
            return {k: self._to_dict(v) for k, v in obj.items()}
        return obj

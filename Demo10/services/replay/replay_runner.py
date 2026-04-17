import uuid
import shutil
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from services.execution.engine import ExecutionEngine
from services.execution.logger import ExecutionLogger
from .models import ReplayRequest, ReplayResult, ReplayComparison
from .replay_loader import ReplayArtifactLoader
from .comparison_engine import ComparisonEngine
from .verdicts import VerdictEngine
from .reporting import ReplayReporter

class ReplayRunner:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.loader = ReplayArtifactLoader(workspace_root)
        self.comparison_engine = ComparisonEngine()
        self.verdict_engine = VerdictEngine()
        self.reporter = ReplayReporter(workspace_root)
        self.replays_dir = workspace_root / "runtime_data" / "replays"
        self.replays_dir.mkdir(parents=True, exist_ok=True)

    def run_replay(self, request: ReplayRequest) -> ReplayResult:
        print(f"REPLAY START")
        print(f"Mode: {request.mode}")
        print(f"Source Run: {request.source_run_id}")
        print(f"Workspace Mode: {request.workspace_mode}")

        try:
            artifacts = self.loader.load_run_artifacts(request.source_run_id)
        except Exception as e:
            print(f"REPLAY_ARTIFACT_MISSING: {str(e)}")
            # For simplicity, returning a failed result here
            return self._failed_result(request, "REPLAY_ARTIFACT_MISSING", str(e))

        source_run = artifacts["run"]
        source_plan = artifacts["plan"]

        replay_run = None
        replay_plan = source_plan # In Replay we use the same plan

        if request.mode == "trace_replay":
            replay_run = source_run
            print(f"TRACE REPLAY START")
            print(f"Loaded {len(replay_run.step_results)} steps")
            print(f"FINAL OUTCOME: {replay_run.status}")
            print(f"CONSISTENCY OUTCOME: {replay_run.consistency_outcome}")
            print(f"TRACE REPLAY COMPLETED")
        else:
            # re_execute
            replay_workspace = self._prepare_workspace(request)
            engine = ExecutionEngine(replay_workspace)
            # Override logger to use replay-specific directory
            replay_run_id = f"replay_{request.replay_id}"
            engine.logger = ExecutionLogger(self.replays_dir / request.replay_id)

            # Actually execute the stored plan
            replay_run = engine.execute(replay_plan)

        comparison = self.comparison_engine.compare(source_run, replay_run, source_plan, replay_plan)
        verdict = self.verdict_engine.determine_verdict(comparison)

        result = ReplayResult(
            replay_id=request.replay_id,
            source_run_id=request.source_run_id,
            mode=request.mode,
            status="completed" if verdict != "mismatch" else "mismatch",
            reproducibility_verdict=verdict,
            comparison=comparison
        )

        self.reporter.save_report(result)

        print(f"\nPLAN MATCH: {'yes' if comparison.plan_match else 'no'}")
        print(f"STEP ORDER MATCH: {'yes' if comparison.step_order_match else 'no'}")
        print(f"STATUS MATCH: {'yes' if comparison.status_match else 'no'}")
        print(f"OUTPUT MATCH: {'yes' if comparison.outputs_match else 'no'}")
        print(f"ROLLBACK MATCH: {'yes' if comparison.rollback_match else 'no'}")
        print(f"\nREPRODUCIBILITY VERDICT: {verdict}")

        return result

    def _prepare_workspace(self, request: ReplayRequest) -> Path:
        if request.workspace_mode == "in_place":
            return self.workspace_root

        if request.workspace_mode == "cloned_workspace":
            clone_path = self.workspace_root.parent / f"workspace_clone_{request.replay_id}"
            if clone_path.exists():
                shutil.rmtree(clone_path)
            shutil.copytree(self.workspace_root, clone_path, ignore=shutil.ignore_patterns('runtime_data'))
            return clone_path

        if request.workspace_mode == "temp_workspace":
            temp_path = self.workspace_root.parent / f"workspace_temp_{request.replay_id}"
            if temp_path.exists():
                shutil.rmtree(temp_path)
            temp_path.mkdir(parents=True)
            return temp_path

        return self.workspace_root

    def _failed_result(self, request: ReplayRequest, code: str, message: str) -> ReplayResult:
        # Minimal failed result
        return ReplayResult(
            replay_id=request.replay_id,
            source_run_id=request.source_run_id,
            mode=request.mode,
            status="failed",
            reproducibility_verdict="not_comparable",
            comparison=ReplayComparison(False, False, False, False, False, False, [])
        )

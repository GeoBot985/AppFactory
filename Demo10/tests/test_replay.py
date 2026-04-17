import unittest
import shutil
import os
import json
from pathlib import Path
from datetime import datetime

from services.execution.engine import ExecutionEngine
from services.planner.models import ExecutionPlan, Step, StepContract
from services.replay.models import ReplayRequest
from services.replay.replay_runner import ReplayRunner

class TestReplay(unittest.TestCase):
    def setUp(self):
        self.workspace_root = Path("Demo10/test_workspace")
        if self.workspace_root.exists():
            shutil.rmtree(self.workspace_root)
        self.workspace_root.mkdir(parents=True)

        # Create necessary directories
        (self.workspace_root / "runtime_data" / "compiler_runs").mkdir(parents=True)
        (self.workspace_root / "runtime_data" / "execution_plans").mkdir(parents=True)
        (self.workspace_root / "runtime_data" / "runs").mkdir(parents=True)

    def tearDown(self):
        if self.workspace_root.exists():
            shutil.rmtree(self.workspace_root)

    def test_trace_replay_success(self):
        # 1. Create a dummy run
        plan_id = "plan_1"
        ir_ref = "ir_1"

        # Dummy IR
        ir_data = {
            "request_id": ir_ref,
            "title": "test",
            "objective": "test",
            "operations": [],
            "compile_status": "compiled_clean"
        }
        with open(self.workspace_root / "runtime_data" / "compiler_runs" / f"{ir_ref}.json", "w") as f:
            json.dump(ir_data, f)

        # Dummy Plan
        step_id = "step_1"
        plan = ExecutionPlan(
            plan_id=plan_id,
            ir_ref=ir_ref,
            steps={
                step_id: Step(
                    step_id=step_id,
                    step_type="analyze_code",
                    target=".",
                    inputs={},
                    contract=StepContract(compensation_type="non_reversible")
                )
            },
            root_steps=[step_id],
            status="ready"
        )
        with open(self.workspace_root / "runtime_data" / "execution_plans" / f"{plan_id}.json", "w") as f:
            json.dump(plan.to_dict(), f)

        # Execute it to generate real artifacts
        engine = ExecutionEngine(self.workspace_root)
        run = engine.execute(plan)
        run_id = run.run_id

        # 2. Run trace replay
        runner = ReplayRunner(self.workspace_root)
        request = ReplayRequest(
            replay_id="rep_1",
            source_run_id=run_id,
            mode="trace_replay",
            workspace_mode="in_place"
        )
        result = runner.run_replay(request)

        self.assertEqual(result.reproducibility_verdict, "exact_match")
        self.assertTrue(result.comparison.plan_match)

    def test_re_execute_exact_match(self):
        # 1. Create a deterministic run
        plan_id = "plan_2"
        ir_ref = "ir_2"

        ir_data = {
            "request_id": ir_ref,
            "title": "test",
            "objective": "test",
            "operations": [],
            "compile_status": "compiled_clean"
        }
        with open(self.workspace_root / "runtime_data" / "compiler_runs" / f"{ir_ref}.json", "w") as f:
            json.dump(ir_data, f)

        step_id = "step_1"
        plan = ExecutionPlan(
            plan_id=plan_id,
            ir_ref=ir_ref,
            steps={
                step_id: Step(
                    step_id=step_id,
                    step_type="analyze_code",
                    target=".",
                    inputs={},
                    contract=StepContract(compensation_type="non_reversible")
                )
            },
            root_steps=[step_id],
            status="ready"
        )
        with open(self.workspace_root / "runtime_data" / "execution_plans" / f"{plan_id}.json", "w") as f:
            json.dump(plan.to_dict(), f)

        engine = ExecutionEngine(self.workspace_root)
        run = engine.execute(plan)
        run_id = run.run_id

        # 2. Re-execute
        runner = ReplayRunner(self.workspace_root)
        request = ReplayRequest(
            replay_id="rep_2",
            source_run_id=run_id,
            mode="re_execute",
            workspace_mode="cloned_workspace"
        )
        result = runner.run_replay(request)

        # Since it's analyze_code and it's deterministic (it just returns {} usually), it should match
        self.assertEqual(result.reproducibility_verdict, "exact_match")

    def test_missing_artifact(self):
        runner = ReplayRunner(self.workspace_root)
        request = ReplayRequest(
            replay_id="rep_3",
            source_run_id="non_existent",
            mode="trace_replay",
            workspace_mode="in_place"
        )
        result = runner.run_replay(request)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.reproducibility_verdict, "not_comparable")

if __name__ == "__main__":
    unittest.main()

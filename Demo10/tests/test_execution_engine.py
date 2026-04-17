import unittest
import shutil
import os
import json
from pathlib import Path
from datetime import datetime

from services.planner.models import ExecutionPlan, Step, StepContract
from services.execution.engine import ExecutionEngine
from services.execution.models import Run, StepResult

class TestExecutionEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("Demo10/tests/tmp_execution_test")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir(parents=True)
        self.engine = ExecutionEngine(self.test_dir)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_simple_create_file(self):
        plan = ExecutionPlan(
            plan_id="test_plan",
            ir_ref="test_ir",
            steps={
                "s1": Step(
                    step_id="s1",
                    step_type="create_file",
                    target="test.txt",
                    inputs={"content": "hello world"},
                    contract=StepContract(
                        preconditions=["path_valid"],
                        postconditions=["file_created"]
                    )
                )
            }
        )

        run = self.engine.execute(plan)

        self.assertEqual(run.status, "completed")
        self.assertEqual(run.step_results["s1"].status, "completed")
        self.assertTrue((self.test_dir / "test.txt").exists())
        with open(self.test_dir / "test.txt", "r") as f:
            self.assertEqual(f.read(), "hello world")

    def test_multi_step_plan(self):
        plan = ExecutionPlan(
            plan_id="multi_step",
            ir_ref="test_ir",
            steps={
                "s1": Step(
                    step_id="s1",
                    step_type="create_file",
                    target="a.txt",
                    inputs={"content": "aaa"}
                ),
                "s2": Step(
                    step_id="s2",
                    step_type="write_file",
                    target="b.txt",
                    inputs={"content": "bbb"},
                    dependencies=["s1"]
                )
            }
        )

        run = self.engine.execute(plan)

        self.assertEqual(run.status, "completed")
        self.assertEqual(run.step_results["s1"].status, "completed")
        self.assertEqual(run.step_results["s2"].status, "completed")
        self.assertTrue((self.test_dir / "a.txt").exists())
        self.assertTrue((self.test_dir / "b.txt").exists())

    def test_precondition_failure(self):
        # Invalid path (absolute)
        plan = ExecutionPlan(
            plan_id="pre_fail",
            ir_ref="test_ir",
            steps={
                "s1": Step(
                    step_id="s1",
                    step_type="create_file",
                    target="/absolute/path.txt",
                    contract=StepContract(preconditions=["path_valid"])
                )
            }
        )

        run = self.engine.execute(plan)

        self.assertEqual(run.status, "failed")
        self.assertEqual(run.step_results["s1"].status, "failed")
        self.assertEqual(run.step_results["s1"].error_code, "PRECONDITION_FAILED")

    def test_postcondition_failure(self):
        # We'll mock a postcondition that fails.
        # Actually, let's use 'file_created' but targeting a file we don't actually create?
        # Our handler ALWAYS creates the file if it's 'create_file'.
        # Let's use a dummy handler that doesn't create it?
        # Or just use a non-existent postcondition for now if it returns False by default?
        # Currently ContractEvaluator.evaluate_postconditions returns True for unknown conditions.

        # Let's add a "fail_me" postcondition to ContractEvaluator for testing?
        # Or better, just use "file_created" and a step type that doesn't create it but expects it.

        plan = ExecutionPlan(
            plan_id="post_fail",
            ir_ref="test_ir",
            steps={
                "s1": Step(
                    step_id="s1",
                    step_type="analyze_code", # This handler doesn't create files
                    target="nonexistent.txt",
                    contract=StepContract(postconditions=["file_created"])
                )
            }
        )

        run = self.engine.execute(plan)

        self.assertEqual(run.status, "failed")
        self.assertEqual(run.step_results["s1"].status, "failed")
        self.assertEqual(run.step_results["s1"].error_code, "POSTCONDITION_FAILED")

    def test_dependency_failure(self):
        plan = ExecutionPlan(
            plan_id="dep_fail",
            ir_ref="test_ir",
            steps={
                "s1": Step(
                    step_id="s1",
                    step_type="create_file",
                    target="/invalid", # Fails precondition
                    contract=StepContract(preconditions=["path_valid"])
                ),
                "s2": Step(
                    step_id="s2",
                    step_type="create_file",
                    target="valid.txt",
                    dependencies=["s1"]
                )
            }
        )

        run = self.engine.execute(plan)

        self.assertEqual(run.status, "failed")
        self.assertEqual(run.step_results["s1"].status, "failed")
        # Spec 045 Section 3 says: "Else: mark as skipped"
        # Section 7 says: "mark remaining steps = skipped"
        self.assertEqual(run.step_results["s2"].status, "skipped")

    def test_audit_logs(self):
        plan = ExecutionPlan(
            plan_id="audit_test",
            ir_ref="test_ir",
            steps={
                "s1": Step(
                    step_id="s1",
                    step_type="create_file",
                    target="audit.txt",
                    inputs={"content": "audit log test"}
                )
            }
        )

        run = self.engine.execute(plan)

        run_dir = self.test_dir / "runtime_data" / "runs" / run.run_id
        self.assertTrue(run_dir.exists())
        self.assertTrue((run_dir / "run.json").exists())
        self.assertTrue((run_dir / "steps" / "s1.json").exists())

        with open(run_dir / "run.json", "r") as f:
            data = json.load(f)
            self.assertEqual(data["run_id"], run.run_id)
            self.assertEqual(data["status"], "completed")

if __name__ == "__main__":
    unittest.main()

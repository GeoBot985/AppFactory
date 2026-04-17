import unittest
import shutil
import os
import json
from pathlib import Path
from datetime import datetime
import uuid

from Demo10.services.planner.models import ExecutionPlan, Step, StepContract
from Demo10.services.execution.engine import ExecutionEngine
from Demo10.verification.harness import VerificationHarness

class TestVerificationHarness(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("Demo10/tests/tmp_verification_harness_test")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir(parents=True)

        # Need to setup runtime_data structure
        (self.test_dir / "runtime_data" / "compiler_runs").mkdir(parents=True)
        (self.test_dir / "runtime_data" / "execution_plans").mkdir(parents=True)
        (self.test_dir / "runtime_data" / "runs").mkdir(parents=True)

        self.engine = ExecutionEngine(self.test_dir)
        self.harness = VerificationHarness(self.test_dir)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_full_harness_flow(self):
        # 1. Create a successful run
        ir_ref = "test_ir_049"
        ir_data = {
            "request_id": "req_1",
            "title": "Test IR",
            "compile_status": "compiled_clean",
            "operations": []
        }
        with open(self.test_dir / "runtime_data" / "compiler_runs" / f"{ir_ref}.json", "w") as f:
            json.dump(ir_data, f)

        plan = ExecutionPlan(
            plan_id="plan_049",
            ir_ref=ir_ref,
            steps={
                "s1": Step(
                    step_id="s1",
                    step_type="create_file",
                    target="test_049.txt",
                    inputs={"content": "hello SPEC 049"}
                )
            }
        )

        # Save plan manually as ExecutionEngine might not do it in the right place if we are not careful
        # ExecutionEngine usually saves to workspace/runtime_data/execution_plans?
        # Let's check where it saves.

        plan_path = self.test_dir / "runtime_data" / "execution_plans" / f"{plan.plan_id}.json"
        with open(plan_path, "w") as f:
            # Simple serialization
            json.dump({
                "plan_id": plan.plan_id,
                "ir_ref": plan.ir_ref,
                "steps": {
                    sid: {
                        "step_id": sid,
                        "step_type": s.step_type,
                        "target": s.target,
                        "inputs": s.inputs,
                        "dependencies": s.dependencies,
                        "contract": {
                            "preconditions": s.contract.preconditions,
                            "postconditions": s.contract.postconditions
                        }
                    } for sid, s in plan.steps.items()
                }
            }, f)

        run = self.engine.execute(plan)
        self.assertEqual(run.status, "completed")
        source_run_id = run.run_id

        # 2. Create Golden Run
        golden_run_id = self.harness.create_golden_run(source_run_id, notes="First golden run")
        self.assertTrue(golden_run_id.startswith("golden_"))
        self.assertTrue((self.test_dir / "runtime_data" / "golden_runs" / golden_run_id).exists())

        # 3. Create Suite
        suite_id = "suite_alpha"
        self.harness.create_suite(suite_id, [golden_run_id], "Alpha testing suite")
        self.assertTrue((self.test_dir / "runtime_data" / "verification_suites" / f"{suite_id}.json").exists())

        # 4. Run Suite (Tolerant)
        result = self.harness.run_suite(suite_id, mode="tolerant")

        self.assertEqual(result.suite_id, suite_id)
        self.assertEqual(len(result.run_results), 1)
        self.assertEqual(result.run_results[0].golden_run_id, golden_run_id)
        # In this simple test, it's structural_match -> pass (in tolerant it's pass/warn)
        # Actually our classifier maps structural_match to 'pass' regardless of mode.
        # outcome_match maps to 'warn'.
        self.assertEqual(result.run_results[0].classification, "pass")
        self.assertEqual(result.overall_verdict, "pass")

        # 5. Run Suite (Strict) - Should still pass if it's 'pass', but let's test corruption
        # Corrupt it
        with open(self.test_dir / "runtime_data" / "golden_runs" / golden_run_id / "ir.json", "w") as f:
            f.write("CORRUPTED")

        result_strict = self.harness.run_suite(suite_id, mode="strict")
        self.assertEqual(result_strict.overall_verdict, "fail")
        self.assertEqual(result_strict.run_results[0].drift_categories, ["environment_drift"])

        # 5. Check Reports
        report_dir = self.test_dir / "runtime_data" / "verification" / suite_id
        self.assertTrue(report_dir.exists())
        # It should have a timestamped subfolder
        subfolders = list(report_dir.iterdir())
        self.assertTrue(len(subfolders) >= 1)

        latest_report = subfolders[0]
        self.assertTrue((latest_report / "summary.json").exists())
        self.assertTrue((latest_report / "detailed_report.json").exists())
        self.assertTrue((latest_report / "report.html").exists())

if __name__ == "__main__":
    unittest.main()

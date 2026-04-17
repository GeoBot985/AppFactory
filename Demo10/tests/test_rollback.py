import unittest
import shutil
import os
from pathlib import Path
from datetime import datetime

from services.planner.models import ExecutionPlan, Step, StepContract
from services.execution.engine import ExecutionEngine
from services.execution.models import Run

class TestRollback(unittest.TestCase):
    def setUp(self):
        self.workspace_root = Path("Demo10/test_workspace")
        if self.workspace_root.exists():
            shutil.rmtree(self.workspace_root)
        self.workspace_root.mkdir(parents=True)
        self.engine = ExecutionEngine(self.workspace_root)

    def tearDown(self):
        if self.workspace_root.exists():
            shutil.rmtree(self.workspace_root)

    def test_create_file_rollback(self):
        # 1. create_file then downstream failure
        plan = ExecutionPlan(
            plan_id="test_create",
            ir_ref="ir_1",
            steps={
                "s1": Step(
                    step_id="s1",
                    step_type="create_file",
                    target="test.txt",
                    inputs={"content": "hello"},
                    contract=StepContract(compensation_type="reversible", compensation_template="delete_created_file")
                ),
                "s2": Step(
                    step_id="s2",
                    step_type="run_command",
                    inputs={"command": "exit 1"},
                    dependencies=["s1"],
                    contract=StepContract(compensation_type="non_reversible")
                )
            },
            root_steps=["s1"],
            terminal_steps=["s2"],
            status="ready"
        )

        run = self.engine.execute(plan)

        self.assertEqual(run.status, "failed")
        self.assertEqual(run.rollback_status, "completed")
        self.assertEqual(run.consistency_outcome, "clean")
        self.assertFalse((self.workspace_root / "test.txt").exists())

    def test_modify_file_rollback(self):
        # 2. modify_file then failure
        test_file = self.workspace_root / "modify.txt"
        with open(test_file, "w") as f:
            f.write("original")

        plan = ExecutionPlan(
            plan_id="test_modify",
            ir_ref="ir_2",
            steps={
                "s1": Step(
                    step_id="s1",
                    step_type="modify_file",
                    target="modify.txt",
                    inputs={"content": "modified"},
                    contract=StepContract(compensation_type="reversible", compensation_template="restore_file_backup")
                ),
                "s2": Step(
                    step_id="s2",
                    step_type="run_command",
                    inputs={"command": "exit 1"},
                    dependencies=["s1"],
                    contract=StepContract(compensation_type="non_reversible")
                )
            },
            root_steps=["s1"],
            terminal_steps=["s2"],
            status="ready"
        )

        run = self.engine.execute(plan)

        self.assertEqual(run.status, "failed")
        self.assertEqual(run.rollback_status, "completed")
        self.assertEqual(run.consistency_outcome, "clean")

        with open(test_file, "r") as f:
            self.assertEqual(f.read(), "original")

    def test_create_and_modify_rollback(self):
        # 3. create + modify same file
        plan = ExecutionPlan(
            plan_id="test_create_modify",
            ir_ref="ir_3",
            steps={
                "s1": Step(
                    step_id="s1",
                    step_type="create_file",
                    target="test.txt",
                    inputs={"content": "created"},
                    contract=StepContract(compensation_type="reversible", compensation_template="delete_created_file")
                ),
                "s2": Step(
                    step_id="s2",
                    step_type="modify_file",
                    target="test.txt",
                    inputs={"content": "modified"},
                    dependencies=["s1"],
                    contract=StepContract(compensation_type="reversible", compensation_template="restore_file_backup")
                ),
                "s3": Step(
                    step_id="s3",
                    step_type="run_command",
                    inputs={"command": "exit 1"},
                    dependencies=["s2"],
                    contract=StepContract(compensation_type="non_reversible")
                )
            },
            root_steps=["s1"],
            terminal_steps=["s3"],
            status="ready"
        )

        run = self.engine.execute(plan)

        self.assertEqual(run.status, "failed")
        self.assertEqual(run.rollback_status, "completed")
        self.assertEqual(run.consistency_outcome, "clean")
        self.assertFalse((self.workspace_root / "test.txt").exists())

    def test_non_reversible_command(self):
        # 5. non-reversible command
        plan = ExecutionPlan(
            plan_id="test_non_reversible",
            ir_ref="ir_5",
            steps={
                "s1": Step(
                    step_id="s1",
                    step_type="run_command",
                    inputs={"command": "echo 'side effect'"},
                    contract=StepContract(compensation_type="non_reversible")
                ),
                "s2": Step(
                    step_id="s2",
                    step_type="run_command",
                    inputs={"command": "exit 1"},
                    dependencies=["s1"],
                    contract=StepContract(compensation_type="non_reversible")
                )
            },
            root_steps=["s1"],
            terminal_steps=["s2"],
            status="ready"
        )

        run = self.engine.execute(plan)

        self.assertEqual(run.status, "failed")
        self.assertEqual(run.rollback_status, "not_needed")
        self.assertEqual(run.consistency_outcome, "not_restored")

if __name__ == "__main__":
    unittest.main()

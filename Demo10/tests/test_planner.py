import unittest
from services.input_compiler.models import CompiledSpecIR, OperationIR, OperationType, CompileStatus
from services.planner.plan_builder import PlanBuilder
from services.planner.models import Step

class TestPlanBuilder(unittest.TestCase):
    def setUp(self):
        self.builder = PlanBuilder()

    def test_simple_create_file(self):
        ir = CompiledSpecIR(
            request_id="req_1",
            title="Create app",
            objective="Build a small app",
            compile_status=CompileStatus.COMPILED_CLEAN,
            operations=[
                OperationIR(op_type=OperationType.CREATE_FILE, target="main.py", instruction="Create main app")
            ]
        )
        plan = self.builder.build_plan(ir)
        self.assertEqual(plan.status, "ready")
        self.assertEqual(len(plan.steps), 3) # validate_path, create_file, verify_file_exists

        # Check linear dependency
        s0 = plan.steps["op_0_s0"]
        s1 = plan.steps["op_0_s1"]
        s2 = plan.steps["op_0_s2"]
        self.assertEqual(s1.dependencies, ["op_0_s0"])
        self.assertEqual(s2.dependencies, ["op_0_s1"])

    def test_create_and_modify_same_file(self):
        ir = CompiledSpecIR(
            request_id="req_2",
            title="Update app",
            objective="Create and then update",
            compile_status=CompileStatus.COMPILED_CLEAN,
            operations=[
                OperationIR(op_type=OperationType.CREATE_FILE, target="a.py", instruction="Init A"),
                OperationIR(op_type=OperationType.MODIFY_FILE, target="a.py", instruction="Update A")
            ]
        )
        plan = self.builder.build_plan(ir)
        self.assertEqual(plan.status, "ready")

        # op_0 has 3 steps (op_0_s0, s1, s2)
        # op_1 has 5 steps (op_1_s0, s1, s2, s3, s4)
        self.assertEqual(len(plan.steps), 8)

        # op_1_s0 (first step of modify) should depend on op_0_s2 (last step of create)
        s_modify_start = plan.steps["op_1_s0"]
        self.assertIn("op_0_s2", s_modify_start.dependencies)

    def test_conflicting_writes(self):
        # We need a way to trigger UNORDERED_WRITES.
        # PlanBuilder currently processes IR operations in order,
        # so it inherently orders same-target ops.
        # To test the validator, we can manually create a plan.
        from services.planner.models import ExecutionPlan, Step
        plan = ExecutionPlan(plan_id="p1", ir_ref="r1")
        plan.steps = {
            "s1": Step(step_id="s1", step_type="write_file", target="f1"),
            "s2": Step(step_id="s2", step_type="write_file", target="f1")
        }
        from services.planner.plan_validator import PlanValidator
        validator = PlanValidator()
        issues = validator.validate(plan)
        self.assertTrue(any(i.code == "UNORDERED_WRITES" for i in issues))

    def test_cyclic_dependency(self):
        from services.planner.models import ExecutionPlan, Step
        plan = ExecutionPlan(plan_id="p1", ir_ref="r1")
        plan.steps = {
            "s1": Step(step_id="s1", step_type="run_command", dependencies=["s2"]),
            "s2": Step(step_id="s2", step_type="run_command", dependencies=["s1"])
        }
        from services.planner.plan_validator import PlanValidator
        validator = PlanValidator()
        issues = validator.validate(plan)
        self.assertTrue(any(i.code == "CYCLIC_DEPENDENCY" for i in issues))

if __name__ == "__main__":
    unittest.main()

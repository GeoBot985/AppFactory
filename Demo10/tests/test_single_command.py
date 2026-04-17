import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch
from Demo10.orchestrator.single_command import SingleCommandOrchestrator
from Demo10.orchestrator.models import SingleCommandRequest, SingleCommandResult
from Demo10.services.input_compiler.models import CompiledSpecIR, CompileStatus
from Demo10.services.planner.models import ExecutionPlan
from Demo10.services.execution.models import Run
from Demo10.verification.models import VerificationResult
from Demo10.services.policy.models import PromotionDecision

class TestSingleCommandOrchestrator(unittest.TestCase):
    def setUp(self):
        self.compiler = MagicMock()
        self.plan_builder = MagicMock()
        self.verification_harness = MagicMock()
        self.promotion_engine = MagicMock()
        self.workspace_root = Path("/tmp/test_workspace")
        self.orchestrator = SingleCommandOrchestrator(
            self.compiler, self.plan_builder, self.verification_harness, self.promotion_engine, self.workspace_root
        )

    @patch("Demo10.orchestrator.single_command.execute_plan")
    @patch("Demo10.orchestrator.reporting.generate_html_report")
    def test_happy_path(self, mock_report, mock_execute):
        # Setup mocks
        ir = CompiledSpecIR(request_id="ir_1", title="T", objective="O", compile_status=CompileStatus.COMPILED_CLEAN)
        self.compiler.compile.return_value = (ir, [])

        plan = ExecutionPlan(plan_id="plan_1", ir_ref="ir_1", status="ready")
        self.plan_builder.build_plan.return_value = plan

        run_result = Run(run_id="run_1", plan_id="plan_1", status="completed")
        from Demo10.services.execution.models import StepResult
        run_result.step_results = {"s1": StepResult(step_id="s1", status="completed")}
        mock_execute.return_value = run_result

        v_result = VerificationResult(suite_id="s1", run_results=[], overall_verdict="pass", summary={})
        self.verification_harness.run_suite.return_value = v_result

        p_decision = PromotionDecision(candidate_id="c1", decision="approved", reasons=[], policy_snapshot={}, evaluated_at=datetime.now())
        self.promotion_engine.evaluate_promotion.return_value = p_decision

        request = SingleCommandRequest(
            request_id="req_1",
            input_text="Do something",
            target_environment="dev",
            strictness="strict",
            workspace_mode="in_place"
        )

        result = self.orchestrator.run_single_command(request)

        self.assertEqual(result.final_status, "completed")
        self.assertEqual(result.compile_status, "ok")
        self.assertEqual(result.plan_id, "plan_1")
        self.assertEqual(result.run_id, "run_1")

    @patch("Demo10.orchestrator.reporting.generate_html_report")
    def test_compile_blocked_no_repair(self, mock_report):
        ir = CompiledSpecIR(request_id="ir_1", title="T", objective="O", compile_status=CompileStatus.BLOCKED)
        self.compiler.compile.return_value = (ir, ["Some issue"])

        request = SingleCommandRequest(
            request_id="req_blocked",
            input_text="Do something",
            target_environment="dev",
            strictness="strict",
            workspace_mode="in_place",
            allow_repair=False
        )

        result = self.orchestrator.run_single_command(request)
        self.assertEqual(result.final_status, "blocked")

if __name__ == "__main__":
    unittest.main()

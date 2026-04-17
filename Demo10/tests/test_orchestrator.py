import unittest
from Demo10.orchestrator.controller import OrchestratorController
from Demo10.orchestrator.stages import OrchestratorStage
from Demo10.orchestrator.run_model import StageStatus

class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        self.orchestrator = OrchestratorController({})

    def test_full_pipeline_flow(self):
        run = self.orchestrator.create_run("Test request")
        self.assertEqual(run.current_stage, OrchestratorStage.REQUEST_RECEIVED.value)

        self.orchestrator.advance_stage(run, OrchestratorStage.NORMALIZATION)
        self.assertEqual(run.current_stage, OrchestratorStage.NORMALIZATION.value)
        self.assertEqual(run.stages[OrchestratorStage.REQUEST_RECEIVED.value].status, StageStatus.COMPLETED)
        self.assertEqual(run.stages[OrchestratorStage.NORMALIZATION.value].status, StageStatus.RUNNING)

    def test_invalid_transition(self):
        run = self.orchestrator.create_run("Test request")
        with self.assertRaises(RuntimeError):
            # Cannot skip stages normally
            self.orchestrator.advance_stage(run, OrchestratorStage.EXECUTION)

    def test_failure_path(self):
        run = self.orchestrator.create_run("Test request")
        self.orchestrator.handle_stage_failure(run, "Something went wrong")
        self.assertEqual(run.current_stage, OrchestratorStage.FAILED.value)
        self.assertEqual(run.stages[OrchestratorStage.REQUEST_RECEIVED.value].status, StageStatus.FAILED)
        self.assertIn("Something went wrong", run.stages[OrchestratorStage.REQUEST_RECEIVED.value].errors)

    def test_await_user_path(self):
        run = self.orchestrator.create_run("Test request")
        self.orchestrator.advance_stage(run, OrchestratorStage.NORMALIZATION)
        self.orchestrator.advance_stage(run, OrchestratorStage.INTENT_DECOMPOSITION)
        self.orchestrator.advance_stage(run, OrchestratorStage.PLANNING_SKELETON)
        self.orchestrator.advance_stage(run, OrchestratorStage.CLARIFICATION_GATE)
        self.orchestrator.await_user(run)

        self.assertEqual(run.current_stage, OrchestratorStage.AWAITING_USER.value)
        self.assertEqual(run.stages[OrchestratorStage.CLARIFICATION_GATE.value].status, StageStatus.AWAITING_USER)

if __name__ == "__main__":
    unittest.main()

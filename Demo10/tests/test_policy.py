import unittest
import json
from pathlib import Path
from services.policy.models import RiskClass, PolicyConfig, PolicyDecision
from services.policy.risk_classifier import RiskClassifier
from services.policy.evaluator import PolicyEvaluator
from services.task_service import Task, TaskType

class TestPolicy(unittest.TestCase):
    def setUp(self):
        self.config = PolicyConfig()
        self.classifier = RiskClassifier(self.config)
        self.evaluator = PolicyEvaluator(self.config)

    def test_risk_classification_by_type(self):
        # ensure_import -> R0 (wait, I implemented CREATE as R0, MODIFY as R1)
        # SPEC 017 says: ensure_import -> R0
        task_create = Task(id="t1", type=TaskType.CREATE, target="new.py")
        res = self.classifier.classify_task(task_create)
        self.assertEqual(res["risk"], RiskClass.R0_LOW.value)

        task_modify = Task(id="t2", type=TaskType.MODIFY, target="old.py")
        res = self.classifier.classify_task(task_modify)
        self.assertEqual(res["risk"], RiskClass.R1_MODERATE.value)

        task_delete = Task(id="t3", type=TaskType.DELETE, target="old.py")
        res = self.classifier.classify_task(task_delete)
        self.assertEqual(res["risk"], RiskClass.R2_HIGH.value)

    def test_risk_classification_by_path(self):
        # Protected path
        task = Task(id="t1", type=TaskType.MODIFY, target="src/policy/models.py")
        res = self.classifier.classify_task(task)
        self.assertEqual(res["risk"], RiskClass.R2_HIGH.value)
        self.assertTrue("high-risk path" in res["reasons"][1])

        # Critical path
        task = Task(id="t2", type=TaskType.MODIFY, target="config/settings.yaml")
        res = self.classifier.classify_task(task)
        self.assertEqual(res["risk"], RiskClass.R3_CRITICAL.value)

    def test_risk_classification_delete_block(self):
        task = Task(id="t1", type=TaskType.MODIFY, target="file.py", constraints=json.dumps({"operation": "delete_block"}))
        res = self.classifier.classify_task(task)
        self.assertEqual(res["risk"], RiskClass.R2_HIGH.value)

    def test_policy_evaluation_pre_execution_allowed(self):
        tasks = [Task(id="t1", type=TaskType.CREATE, target="new.py")]
        assessment = self.classifier.classify(tasks)
        result = self.evaluator.evaluate_pre_execution("run_1", assessment)
        self.assertEqual(result.decision, PolicyDecision.POLICY_ALLOWED.value)

    def test_policy_evaluation_pre_execution_approval_required(self):
        # Delete requires approval
        tasks = [Task(id="t1", type=TaskType.DELETE, target="old.py")]
        assessment = self.classifier.classify(tasks)
        result = self.evaluator.evaluate_pre_execution("run_1", assessment)
        self.assertEqual(result.decision, PolicyDecision.APPROVAL_REQUIRED.value)
        self.assertIn("FILE_DELETE_OPERATION", result.reason_codes)

    def test_policy_evaluation_pre_execution_denied(self):
        # Denied executable
        task = Task(id="t1", type=TaskType.RUN, target="rm -rf /")
        assessment = self.classifier.classify([task])
        result = self.evaluator.evaluate_pre_execution("run_1", assessment)
        self.assertEqual(result.decision, PolicyDecision.POLICY_DENIED.value)
        self.assertIn("DENIED_EXECUTABLE", result.reason_codes)

    def test_policy_evaluation_pre_promotion_approval_required(self):
        # Changed file count above threshold (default 5)
        facts = {
            "changed_file_count": 7,
            "contains_deletion": False,
            "touches_protected_path": False,
            "final_status": "COMPLETED"
        }
        risk, _ = self.classifier.classify_actual_promotion(facts)
        result = self.evaluator.evaluate_pre_promotion("run_1", risk, facts)
        self.assertEqual(result.decision, PolicyDecision.APPROVAL_REQUIRED.value)
        self.assertIn("PROMOTION_RISK_ABOVE_AUTO_THRESHOLD", result.reason_codes)

    def test_policy_evaluation_pre_promotion_denied(self):
        facts = {
            "changed_file_count": 1,
            "final_status": "FAILED"
        }
        risk, _ = self.classifier.classify_actual_promotion(facts)
        result = self.evaluator.evaluate_pre_promotion("run_1", risk, facts)
        self.assertEqual(result.decision, PolicyDecision.POLICY_DENIED.value)

if __name__ == "__main__":
    unittest.main()

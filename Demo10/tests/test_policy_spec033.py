import unittest
from pathlib import Path
from services.policy.engine import PolicyEngine
from services.policy.models import PolicyConfig, PolicyDomain, PolicyDecision, ScopePolicy, RiskPolicy, ExecutionPolicy, RerunPolicy, RestorePolicy

class TestPolicyEngineSpec033(unittest.TestCase):
    def setUp(self):
        self.config = PolicyConfig()
        self.engine = PolicyEngine(self.config)

    def test_max_edit_files_enforced(self):
        self.config.scope.max_edit_files = 2
        context = {"files_touched": 3}
        result = self.engine.evaluate(PolicyDomain.COMPILE, "test_run", context)
        self.assertEqual(result.decision, PolicyDecision.BLOCK.value)
        self.assertIn("max_edit_files_exceeded", result.reasons[0])

    def test_high_risk_requires_approval(self):
        self.config.risk.require_approval_above = "R1_MODERATE"
        context = {"risk_class": "R2_HIGH"}
        result = self.engine.evaluate(PolicyDomain.PREVIEW, "test_run", context)
        self.assertEqual(result.decision, PolicyDecision.WARN.value)
        self.assertIn("risk_level_requires_approval", result.reasons[0])

    def test_high_risk_blocked_if_configured(self):
        self.config.risk.allow_high_risk = False
        context = {"risk_class": "R2_HIGH"}
        result = self.engine.evaluate(PolicyDomain.PREVIEW, "test_run", context)
        self.assertEqual(result.decision, PolicyDecision.BLOCK.value)
        self.assertIn("high_risk_not_allowed", result.reasons[0])

    def test_retry_limit_enforced(self):
        self.config.execution.max_attempts_per_task = 3
        context = {"attempts": 3}
        result = self.engine.evaluate(PolicyDomain.TASK, "test_task", context)
        self.assertEqual(result.decision, PolicyDecision.BLOCK.value)
        self.assertIn("max_attempts_per_task_exceeded", result.reasons[0])

    def test_restore_drift_policy(self):
        self.config.restore.allow_restore_on_drift = False
        context = {"has_drift": True}
        result = self.engine.evaluate(PolicyDomain.RESTORE, "test_restore", context)
        self.assertEqual(result.decision, PolicyDecision.BLOCK.value)
        self.assertIn("restore_blocked_on_drift", result.reasons[0])

    def test_rerun_depth_enforced(self):
        self.config.rerun.max_rerun_depth = 5
        context = {"rerun_depth": 6}
        result = self.engine.evaluate(PolicyDomain.RERUN, "test_rerun", context)
        self.assertEqual(result.decision, PolicyDecision.BLOCK.value)
        self.assertIn("max_rerun_depth_exceeded", result.reasons[0])

    def test_denied_executable_enforced(self):
        self.config.risk.denied_executables = ["rm"]
        context = {"commands": ["rm -rf /"]}
        result = self.engine.evaluate(PolicyDomain.TASK, "test_task", context)
        self.assertEqual(result.decision, PolicyDecision.BLOCK.value)
        self.assertIn("denied_executable_detected", result.reasons[0])

if __name__ == "__main__":
    unittest.main()

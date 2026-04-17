import unittest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from Demo10.services.policy.models import PromotionCandidate, PromotionPolicy, EnvironmentPolicy
from Demo10.services.policy.policies import DEFAULT_PROMOTION_POLICY
from Demo10.services.policy.promotion_engine import PromotionEngine
from Demo10.services.policy.audit import PromotionAuditService
from Demo10.verification.models import VerificationResult, GoldenRunResult

class TestPromotionEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.audit_service = PromotionAuditService(self.test_dir)
        self.engine = PromotionEngine(DEFAULT_PROMOTION_POLICY, self.audit_service)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_dev_promotion_with_warnings(self):
        candidate = PromotionCandidate(
            candidate_id="cand_dev_1",
            source_environment="dev",
            target_environment="dev",
            system_version="v1.0.0",
            verification_suite_id="suite_1",
            verification_result_id="res_1",
            timestamp=datetime.now()
        )

        result = VerificationResult(
            suite_id="suite_1",
            run_results=[
                GoldenRunResult(
                    golden_run_id="gr_1",
                    replay_result=None,
                    verdict="structural_match",
                    classification="warn",
                    drift_categories=["environment_drift"]
                )
            ],
            overall_verdict="pass_with_warnings",
            summary={"warn_count": 1, "fail_count": 0}
        )

        decision = self.engine.evaluate_promotion(candidate, result)
        self.assertEqual(decision.decision, "approved_with_warnings")
        self.assertEqual(len(decision.reasons), 0)

    def test_staging_promotion_with_blocked_drift(self):
        candidate = PromotionCandidate(
            candidate_id="cand_staging_1",
            source_environment="dev",
            target_environment="staging",
            system_version="v1.0.0",
            verification_suite_id="suite_1",
            verification_result_id="res_1",
            timestamp=datetime.now()
        )

        result = VerificationResult(
            suite_id="suite_1",
            run_results=[
                GoldenRunResult(
                    golden_run_id="gr_1",
                    replay_result=None,
                    verdict="structural_match",
                    classification="pass",
                    drift_categories=["plan_drift"]
                )
            ],
            overall_verdict="pass",
            summary={"warn_count": 0, "fail_count": 0}
        )

        decision = self.engine.evaluate_promotion(candidate, result)
        self.assertEqual(decision.decision, "rejected")
        self.assertTrue(any("PROMOTION_REJECTED_DRIFT" in r for r in decision.reasons))

    def test_prod_promotion_with_warnings_rejected(self):
        candidate = PromotionCandidate(
            candidate_id="cand_prod_1",
            source_environment="staging",
            target_environment="prod",
            system_version="v1.0.0",
            verification_suite_id="suite_1",
            verification_result_id="res_1",
            timestamp=datetime.now()
        )

        result = VerificationResult(
            suite_id="suite_1",
            run_results=[
                GoldenRunResult(
                    golden_run_id="gr_1",
                    replay_result=None,
                    verdict="exact_match",
                    classification="warn",
                    drift_categories=[]
                )
            ],
            overall_verdict="pass_with_warnings",
            summary={"warn_count": 1, "fail_count": 0}
        )

        decision = self.engine.evaluate_promotion(candidate, result)
        self.assertEqual(decision.decision, "rejected")
        self.assertTrue(any("PROMOTION_REJECTED_VERDICT" in r for r in decision.reasons))
        self.assertTrue(any("PROMOTION_REJECTED_WARNINGS" in r for r in decision.reasons))

    def test_prod_promotion_exact_pass_approved(self):
        candidate = PromotionCandidate(
            candidate_id="cand_prod_2",
            source_environment="staging",
            target_environment="prod",
            system_version="v1.0.0",
            verification_suite_id="suite_1",
            verification_result_id="res_1",
            timestamp=datetime.now()
        )

        result = VerificationResult(
            suite_id="suite_1",
            run_results=[
                GoldenRunResult(
                    golden_run_id="gr_1",
                    replay_result=None,
                    verdict="exact_match",
                    classification="pass",
                    drift_categories=[]
                )
            ],
            overall_verdict="pass",
            summary={"warn_count": 0, "fail_count": 0}
        )

        decision = self.engine.evaluate_promotion(candidate, result)
        self.assertEqual(decision.decision, "approved")
        self.assertEqual(len(decision.reasons), 0)

    def test_staging_not_comparable_rejected(self):
        candidate = PromotionCandidate(
            candidate_id="cand_staging_2",
            source_environment="dev",
            target_environment="staging",
            system_version="v1.0.0",
            verification_suite_id="suite_1",
            verification_result_id="res_1",
            timestamp=datetime.now()
        )

        result = VerificationResult(
            suite_id="suite_1",
            run_results=[
                GoldenRunResult(
                    golden_run_id="gr_1",
                    replay_result=None,
                    verdict="fail", # represents not comparable
                    classification="fail",
                    drift_categories=[]
                )
            ],
            overall_verdict="fail",
            summary={"warn_count": 0, "fail_count": 1}
        )

        decision = self.engine.evaluate_promotion(candidate, result)
        self.assertEqual(decision.decision, "rejected")
        self.assertTrue(any("PROMOTION_REJECTED_NOT_COMPARABLE" in r for r in decision.reasons))

    def test_manual_override(self):
        candidate = PromotionCandidate(
            candidate_id="cand_prod_3",
            source_environment="staging",
            target_environment="prod",
            system_version="v1.0.0",
            verification_suite_id="suite_1",
            verification_result_id="res_1",
            timestamp=datetime.now()
        )

        # This would normally be rejected in prod
        result = VerificationResult(
            suite_id="suite_1",
            run_results=[
                GoldenRunResult(
                    golden_run_id="gr_1",
                    replay_result=None,
                    verdict="exact_match",
                    classification="warn",
                    drift_categories=[]
                )
            ],
            overall_verdict="pass_with_warnings",
            summary={"warn_count": 1, "fail_count": 0}
        )

        decision = self.engine.override_promotion(candidate, result, "Critical fix required")
        self.assertEqual(decision.decision, "approved_with_override")
        self.assertTrue(any("MANUAL_OVERRIDE: Critical fix required" in r for r in decision.reasons))

        # Verify persistence
        history = self.audit_service.get_history("v1.0.0")
        self.assertIsNotNone(history)
        self.assertIn("prod", history.environments_reached)
        self.assertEqual(history.decisions[0].decision, "approved_with_override")

if __name__ == "__main__":
    unittest.main()

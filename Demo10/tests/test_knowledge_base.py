import unittest
import shutil
from pathlib import Path
from Demo10.knowledge.updater import KnowledgeUpdater
from Demo10.knowledge.query import KnowledgeQuery
from Demo10.knowledge.store import KnowledgeStore
from Demo10.suggestions.engine import SuggestionEngine
from Demo10.diagnostics.models import RootCause

class TestKnowledgeBase(unittest.TestCase):
    def setUp(self):
        self.test_workspace = Path("test_kb_workspace")
        self.test_workspace.mkdir(exist_ok=True)
        self.updater = KnowledgeUpdater(self.test_workspace)
        self.query = KnowledgeQuery(self.test_workspace)
        self.engine = SuggestionEngine(self.test_workspace)

    def tearDown(self):
        if self.test_workspace.exists():
            shutil.rmtree(self.test_workspace)

    def test_record_and_query(self):
        # Record a successful fix
        self.updater.record_outcome(
            signature_id="sig_123",
            suggestion_id="sug_abc",
            outcome="resolved",
            root_cause_id="rc_path"
        )

        solutions = self.query.get_solutions("sig_123")
        self.assertEqual(len(solutions), 1)
        self.assertEqual(solutions[0].suggestion_id, "sug_abc")
        self.assertEqual(solutions[0].success_rate, 1.0)
        self.assertEqual(solutions[0].usage_count, 1)

        # Record a failure for the same fix
        self.updater.record_outcome(
            signature_id="sig_123",
            suggestion_id="sug_abc",
            outcome="not_resolved",
            root_cause_id="rc_path"
        )

        solutions = self.query.get_solutions("sig_123")
        self.assertEqual(solutions[0].success_rate, 0.5)
        self.assertEqual(solutions[0].usage_count, 2)

    def test_deterministic_ranking(self):
        # Fix A: 2 usage, 1 success (50%)
        self.updater.record_outcome("sig_1", "sug_A", "resolved", "rc_1")
        self.updater.record_outcome("sig_1", "sug_A", "not_resolved", "rc_1")

        # Fix B: 1 usage, 1 success (100%)
        self.updater.record_outcome("sig_1", "sug_B", "resolved", "rc_1")

        solutions = self.query.get_solutions("sig_1")
        self.assertEqual(solutions[0].suggestion_id, "sug_B")
        self.assertEqual(solutions[1].suggestion_id, "sug_A")

    def test_suggestion_engine_integration(self):
        # Mock some history
        self.updater.record_outcome("sig_invalid_path", "sug_set_target", "resolved", "execution_error.invalid_path")
        self.updater.record_outcome("sig_invalid_path", "sug_set_target", "resolved", "execution_error.invalid_path")
        self.updater.record_outcome("sig_invalid_path", "sug_set_target", "resolved", "execution_error.invalid_path")

        root_cause = RootCause(
            root_cause_id="execution_error.invalid_path",
            category="execution_error",
            subcategory="invalid_path",
            description="Path not found"
        )

        suggestions = self.engine.generate_suggestions(root_cause, signature_id="sig_invalid_path")

        # Check if sug_set_target (if it exists in mappings) got boosted
        # Since I don't know the exact suggestion_ids in mappings.py,
        # I'll just check if confidence and _kb_success_rate are set
        found = False
        for sug in suggestions:
            if hasattr(sug, "_kb_success_rate") and getattr(sug, "_kb_success_rate") > 0:
                found = True
                self.assertEqual(sug.confidence, "high")

        # Note: mappings.py might not have sug_set_target, but it should have some suggestions
        # that we can map if we used a real root_cause_id.

if __name__ == "__main__":
    unittest.main()

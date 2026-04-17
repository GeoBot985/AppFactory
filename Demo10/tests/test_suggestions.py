import unittest
from pathlib import Path
import shutil
import os
from Demo10.suggestions.engine import SuggestionEngine
from Demo10.suggestions.models import RepairSuggestion, SuggestedAction, SuggestionUsage
from Demo10.diagnostics.models import RootCause

class TestSuggestions(unittest.TestCase):
    def setUp(self):
        self.workspace_root = Path("test_suggestions_ws").absolute()
        if self.workspace_root.exists():
            shutil.rmtree(self.workspace_root)
        self.workspace_root.mkdir()
        self.engine = SuggestionEngine(self.workspace_root)

    def tearDown(self):
        if self.workspace_root.exists():
            shutil.rmtree(self.workspace_root)

    def test_generate_suggestions_invalid_path(self):
        rc = RootCause(
            root_cause_id="execution_error.invalid_path",
            category="execution_error",
            subcategory="invalid_path",
            description="Invalid path",
            deterministic=True
        )

        # Create a dummy file to test enrichment
        (self.workspace_root / "target_file.py").touch()

        suggestions = self.engine.generate_suggestions(rc, context_data={"invalid_path": "targt_file.py"})

        self.assertTrue(len(suggestions) > 0)
        self.assertEqual(suggestions[0].root_cause_id, "execution_error.invalid_path")
        self.assertIn("target_file.py", suggestions[0].description)

    def test_deterministic_ranking(self):
        from Demo10.suggestions.ranking import rank_suggestions

        s1 = RepairSuggestion(
            suggestion_id="s1",
            root_cause_id="rc1",
            category="input_fix",
            description="low confidence",
            confidence="low",
            actions=[SuggestedAction(action_type="set_field", instructions="do it")]
        )
        s2 = RepairSuggestion(
            suggestion_id="s2",
            root_cause_id="rc1",
            category="input_fix",
            description="high confidence",
            confidence="high",
            actions=[SuggestedAction(action_type="set_field", instructions="do it"), SuggestedAction(action_type="set_field", instructions="do it again")]
        )
        s3 = RepairSuggestion(
            suggestion_id="s3",
            root_cause_id="rc1",
            category="input_fix",
            description="high confidence few actions",
            confidence="high",
            actions=[SuggestedAction(action_type="set_field", instructions="do it")]
        )

        ranked = rank_suggestions([s1, s2, s3])

        self.assertEqual(ranked[0].suggestion_id, "s3") # High confidence, 1 action
        self.assertEqual(ranked[1].suggestion_id, "s2") # High confidence, 2 actions
        self.assertEqual(ranked[2].suggestion_id, "s1") # Low confidence

    def test_tracking(self):
        usage = SuggestionUsage(
            suggestion_id="test_sug",
            run_id="run_123",
            applied=True,
            resolved_issue=True
        )
        self.engine.tracker.record_usage(usage)

        eff = self.engine.tracker.get_effectiveness()
        self.assertEqual(len(eff), 1)
        self.assertEqual(eff[0].suggestion_id, "test_sug")
        self.assertEqual(eff[0].resolution_count, 1)

    def test_suggestion_to_repair_action(self):
        sug = RepairSuggestion(
            suggestion_id="s1",
            root_cause_id="input_error.missing_target",
            category="input_fix",
            description="Add target",
            confidence="high",
            actions=[
                SuggestedAction(
                    action_type="add_missing_value",
                    target_field="operation.target",
                    instructions="Add the target"
                )
            ]
        )

        repair_actions = self.engine.suggestion_to_repair_action(sug)
        self.assertEqual(len(repair_actions), 1)
        self.assertEqual(repair_actions[0].action_type, "add_missing_field")
        self.assertEqual(repair_actions[0].target_field, "operation.target")

if __name__ == "__main__":
    unittest.main()

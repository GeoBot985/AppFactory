import unittest
from unittest.mock import MagicMock
from Demo10.services.planning.planning_models import IntentType, ConditionType, ComplexityClass, NormalizedRequest, IntentUnit
from Demo10.services.planning.request_normalizer import RequestNormalizer
from Demo10.services.planning.planning_skeleton_builder import SkeletonBuilder

class TestPlanningLayer(unittest.TestCase):
    def setUp(self):
        self.mock_ollama = MagicMock()
        self.normalizer = RequestNormalizer(self.mock_ollama)
        self.builder = SkeletonBuilder()

    def test_single_intent_normalization(self):
        self.mock_ollama.run_prompt.return_value = """
        ```json
        {
          "cleaned_summary": "Add tests for notes app",
          "action_phrases": ["Add tests"],
          "entities": ["notes app"],
          "explicit_constraints": [],
          "unresolved_ambiguities": [],
          "intents": [
            {
              "intent_id": "intent_1",
              "intent_type": "add_tests",
              "summary": "Add tests for notes app",
              "entities": ["notes app"],
              "constraints": [],
              "dependency_hints": [],
              "ambiguities": []
            }
          ]
        }
        ```
        """
        norm = self.normalizer.normalize("mock-model", "Add tests for notes app")
        self.assertEqual(len(norm.intents), 1)
        self.assertEqual(norm.intents[0].intent_type, IntentType.ADD_TESTS)

        skel = self.builder.build(norm)
        self.assertEqual(len(skel.steps), 1)
        self.assertEqual(skel.complexity_class, ComplexityClass.SINGLE_INTENT_SIMPLE)

    def test_multi_intent_linear(self):
        norm = NormalizedRequest(
            request_id="req_1",
            original_text="Build app and then add search",
            cleaned_summary="Build app and search",
            intents=[
                IntentUnit(intent_id="i1", intent_type=IntentType.BUILD_COMPONENT, summary="Build app"),
                IntentUnit(intent_id="i2", intent_type=IntentType.ADD_FEATURE, summary="Add search", dependency_hints=["after i1"])
            ]
        )
        skel = self.builder.build(norm)
        self.assertEqual(len(skel.steps), 2)
        self.assertEqual(skel.steps[1].depends_on, ["step_1"])
        self.assertEqual(skel.complexity_class, ComplexityClass.MULTI_INTENT_LINEAR)

    def test_conditional_dependency(self):
        norm = NormalizedRequest(
            request_id="req_2",
            original_text="Fix bug and if tests pass add UI",
            cleaned_summary="Fix and UI",
            intents=[
                IntentUnit(intent_id="i1", intent_type=IntentType.FIX_BUG, summary="Fix bug"),
                IntentUnit(intent_id="i2", intent_type=IntentType.ADD_UI, summary="Add UI", dependency_hints=["if tests pass"])
            ]
        )
        skel = self.builder.build(norm)
        self.assertEqual(skel.steps[1].condition, ConditionType.ON_SUCCESS)
        self.assertEqual(skel.complexity_class, ComplexityClass.MULTI_INTENT_CONDITIONAL)

    def test_ambiguity_surface(self):
        norm = NormalizedRequest(
            request_id="req_3",
            original_text="Make it better",
            cleaned_summary="Improve",
            unresolved_ambiguities=["'better' is too vague"],
            intents=[IntentUnit(intent_id="i1", intent_type=IntentType.UNKNOWN, summary="Make it better")]
        )
        skel = self.builder.build(norm)
        self.assertIn("'better' is too vague", skel.planning_warnings)
        self.assertEqual(skel.complexity_class, ComplexityClass.MULTI_INTENT_AMBIGUOUS)

if __name__ == "__main__":
    unittest.main()

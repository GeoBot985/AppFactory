from __future__ import annotations
import unittest
from Demo10.services.planning.planning_models import NormalizedRequest, PlanningSkeleton, IntentUnit, IntentType
from Demo10.services.planning.clarification_service import ClarificationService
from Demo10.services.planning.clarification_models import ClarificationSessionStatus, ClarificationIssueType

class TestClarification(unittest.TestCase):
    def setUp(self):
        self.service = ClarificationService()

    def test_no_clarification_needed(self):
        normalized = NormalizedRequest(
            request_id="req1",
            original_text="Add a feature to main.py",
            cleaned_summary="Add feature to main.py",
            entities=["main.py"],
            intents=[
                IntentUnit(
                    intent_id="intent1",
                    intent_type=IntentType.ADD_FEATURE,
                    summary="Add a feature",
                    entities=["main.py"]
                )
            ]
        )
        skeleton = PlanningSkeleton(skeleton_id="skel1", request_id="req1")

        session = self.service.create_session(normalized, skeleton)
        # Note: AMBIGUOUS_ENTRYPOINT (INFO) might still be there but not blocking
        self.assertEqual(session.status, ClarificationSessionStatus.RESOLVED) # RESOLVED means no blocking issues
        self.assertEqual(len(session.questions), 0)

    def test_missing_framework_choice(self):
        normalized = NormalizedRequest(
            request_id="req2",
            original_text="Add a simple UI",
            cleaned_summary="Add UI",
            intents=[
                IntentUnit(
                    intent_id="intent1",
                    intent_type=IntentType.ADD_UI,
                    summary="Add a simple UI"
                )
            ]
        )
        skeleton = PlanningSkeleton(skeleton_id="skel2", request_id="req2")

        session = self.service.create_session(normalized, skeleton)
        self.assertEqual(session.status, ClarificationSessionStatus.AWAITING_USER)
        self.assertTrue(any(q.text.find("framework") != -1 or q.text.find("CLI, Tkinter, or Web") != -1 for q in session.questions))

    def test_ambiguous_target(self):
        normalized = NormalizedRequest(
            request_id="req3",
            original_text="Patch the function",
            cleaned_summary="Patch function",
            intents=[
                IntentUnit(
                    intent_id="intent1",
                    intent_type=IntentType.FIX_BUG,
                    summary="Patch the function"
                )
            ]
        )
        skeleton = PlanningSkeleton(skeleton_id="skel3", request_id="req3")

        session = self.service.create_session(normalized, skeleton)
        self.assertEqual(session.status, ClarificationSessionStatus.AWAITING_USER)
        self.assertTrue(any(i.issue_type == ClarificationIssueType.AMBIGUOUS_TARGET for i in session.issues))

    def test_answer_integration(self):
        normalized = NormalizedRequest(
            request_id="req4",
            original_text="Add a UI",
            cleaned_summary="Add UI",
            intents=[
                IntentUnit(
                    intent_id="intent1",
                    intent_type=IntentType.ADD_UI,
                    summary="Add a UI"
                )
            ]
        )
        skeleton = PlanningSkeleton(skeleton_id="skel4", request_id="req4")

        session = self.service.create_session(normalized, skeleton)
        q_id = session.questions[0].question_id

        self.service.apply_answers(session, {q_id: "Tkinter"}, normalized, skeleton)

        self.assertEqual(session.status, ClarificationSessionStatus.RESOLVED)
        self.assertTrue(any("Use Tkinter framework" in c for c in normalized.intents[0].constraints))

    def test_defer_intent(self):
        normalized = NormalizedRequest(
            request_id="req5",
            original_text="Patch the function",
            cleaned_summary="Patch function",
            intents=[
                IntentUnit(
                    intent_id="intent1",
                    intent_type=IntentType.FIX_BUG,
                    summary="Patch the function"
                )
            ]
        )
        skeleton = PlanningSkeleton(skeleton_id="skel5", request_id="req5")
        session = self.service.create_session(normalized, skeleton)
        q_id = session.questions[0].question_id

        self.service.apply_answers(session, {q_id: "defer"}, normalized, skeleton)

        self.assertEqual(session.status, ClarificationSessionStatus.RESOLVED)
        self.assertTrue(normalized.intents[0].summary.startswith("[DEFERRED]"))
        self.assertTrue("MANUAL_STEP_LATER" in normalized.intents[0].constraints)

if __name__ == "__main__":
    unittest.main()

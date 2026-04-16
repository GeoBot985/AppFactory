from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from .planning_models import NormalizedRequest, PlanningSkeleton, IntentType
from .clarification_models import (
    ClarificationSession, ClarificationSessionStatus, ClarificationIssue,
    ClarificationQuestion, ClarificationIssueType, ResolutionMode
)
from .clarification_detector import ClarificationDetector
from .question_builder import QuestionBuilder

class ClarificationService:
    def __init__(self):
        self.detector = ClarificationDetector()
        self.question_builder = QuestionBuilder()

    def create_session(
        self,
        normalized_request: NormalizedRequest,
        planning_skeleton: PlanningSkeleton,
        session_context: Optional[Dict[str, Any]] = None,
        policy_evaluator: Optional[Any] = None
    ) -> ClarificationSession:
        issues = self.detector.detect_issues(normalized_request, planning_skeleton, session_context=session_context)

        # SPEC 036: Use session memory to resolve issues if possible
        if session_context:
            for issue in issues:
                if issue.issue_type == ClarificationIssueType.AMBIGUOUS_FRAMEWORK:
                    # check if framework was recently used
                    last_template = session_context.get("last_template_id", "")
                    if "tkinter" in last_template.lower():
                        issue.candidate_defaults.insert(0, "Tkinter")
                        # If confidence is high, we might even auto-infer
                elif issue.issue_type == ClarificationIssueType.MISSING_PERSISTENCE_CHOICE:
                    # check recent entries for persistence choice
                    pass

        # SPEC 033: Policy integration
        if policy_evaluator and normalized_request.intents:
            # Check for high-risk choices that might require clarification
            for intent in normalized_request.intents:
                if intent.intent_type == IntentType.REFACTOR_LOCAL and not intent.entities:
                    # Policy might want to force clarification here
                    pass

        # Determine status
        blocking_issues = [i for i in issues if i.resolution_mode in [ResolutionMode.MUST_CLARIFY, ResolutionMode.MUST_BLOCK]]

        status = ClarificationSessionStatus.NO_CLARIFICATION_NEEDED
        questions = []

        if blocking_issues:
            status = ClarificationSessionStatus.AWAITING_USER
            questions = self.question_builder.build_minimal_questions(blocking_issues)
        else:
            # No blocking issues
            status = ClarificationSessionStatus.RESOLVED

        return ClarificationSession(
            session_id=f"clar_{uuid.uuid4().hex[:8]}",
            request_id=normalized_request.request_id,
            normalized_request_id=normalized_request.request_id,
            planning_skeleton_id=planning_skeleton.skeleton_id,
            status=status,
            issues=issues,
            questions=questions,
            updated_at=datetime.now().isoformat()
        )

    def apply_answers(
        self,
        session: ClarificationSession,
        answers: Dict[str, Any],
        normalized_request: NormalizedRequest,
        planning_skeleton: PlanningSkeleton
    ) -> None:
        """Maps answers back to structured planning state."""
        session.answers.update(answers)

        # Apply logic: update normalized_request or planning_skeleton based on answers
        for q_id, answer in answers.items():
            question = next((q for q in session.questions if q.question_id == q_id), None)
            if not question: continue

            for issue_id in question.related_issue_ids:
                issue = next((i for i in session.issues if i.issue_id == issue_id), None)
                if not issue: continue

                # Apply change to normalized_request
                if issue.issue_type == ClarificationIssueType.AMBIGUOUS_FRAMEWORK:
                    for intent_id in issue.related_intent_ids:
                        intent = next((i for i in normalized_request.intents if i.intent_id == intent_id), None)
                        if intent:
                            # Handle grouped answer
                            if " + " in answer:
                                f_choice = answer.split(" + ")[0]
                                intent.constraints.append(f"Use {f_choice} framework")
                            else:
                                intent.constraints.append(f"Use {answer} framework")
                            # Also maybe remove it from ambiguities if it was there
                            if f"Framework for {intent.summary} is ambiguous" in intent.ambiguities:
                                intent.ambiguities.remove(f"Framework for {intent.summary} is ambiguous")

                elif issue.issue_type == ClarificationIssueType.MISSING_PERSISTENCE_CHOICE:
                    for intent_id in issue.related_intent_ids:
                        intent = next((i for i in normalized_request.intents if i.intent_id == intent_id), None)
                        if intent:
                            # Handle grouped answer
                            if " + " in answer:
                                p_choice = answer.split(" + ")[1]
                                intent.constraints.append(f"Use {p_choice} for persistence")
                            else:
                                intent.constraints.append(f"Use {answer} for persistence")

                elif issue.issue_type == ClarificationIssueType.AMBIGUOUS_TARGET:
                    for intent_id in issue.related_intent_ids:
                        intent = next((i for i in normalized_request.intents if i.intent_id == intent_id), None)
                        if intent:
                            if answer.lower() in ["defer", "skip", "manual"]:
                                # Defer this intent
                                intent.summary = f"[DEFERRED] {intent.summary}"
                                intent.constraints.append("MANUAL_STEP_LATER")
                            else:
                                intent.entities.append(answer)

        # Re-check status: only resolved if all blocking questions are answered
        all_answered = True
        for q in session.questions:
            if q.question_id not in session.answers:
                all_answered = False
                break

        if all_answered:
            session.status = ClarificationSessionStatus.RESOLVED
        else:
            session.status = ClarificationSessionStatus.ANSWERED # Partially answered

        session.updated_at = datetime.now().isoformat()

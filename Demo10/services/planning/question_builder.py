from __future__ import annotations
import uuid
from typing import List, Dict, Any
from .clarification_models import ClarificationIssue, ClarificationQuestion, QuestionType, ClarificationIssueType

class QuestionBuilder:
    def build_minimal_questions(self, issues: List[ClarificationIssue]) -> List[ClarificationQuestion]:
        questions = []

        # Group issues by intent to see if they can be combined
        intent_to_issues = {}
        global_issues = []

        for issue in issues:
            if issue.scope == "intent" and issue.related_intent_ids:
                intent_id = issue.related_intent_ids[0]
                if intent_id not in intent_to_issues:
                    intent_to_issues[intent_id] = []
                intent_to_issues[intent_id].append(issue)
            else:
                global_issues.append(issue)

        # Build questions for global issues
        for issue in global_issues:
            if not issue.requires_user_answer:
                continue

            questions.append(self._issue_to_question(issue))

        # Build questions for intent-specific issues, grouping if possible
        for intent_id, i_issues in intent_to_issues.items():
            # SPEC 038: Grouping logic
            # If same intent has multiple choices missing, we group them into one compact multi-select or single question
            # For now, if there's a framework and persistence issue for same intent, let's offer a combined choice

            missing_framework = next((i for i in i_issues if i.issue_type == ClarificationIssueType.AMBIGUOUS_FRAMEWORK), None)
            missing_persistence = next((i for i in i_issues if i.issue_type == ClarificationIssueType.MISSING_PERSISTENCE_CHOICE), None)

            if missing_framework and missing_persistence:
                q_id = f"q_group_{uuid.uuid4().hex[:8]}"
                questions.append(ClarificationQuestion(
                    question_id=q_id,
                    text=f"For the '{i_issues[0].related_intent_ids[0]}' component, please choose a stack:",
                    question_type=QuestionType.SINGLE_SELECT,
                    options=["Tkinter + JSON", "Web + SQLite", "CLI + JSON"],
                    related_issue_ids=[missing_framework.issue_id, missing_persistence.issue_id]
                ))
                # Add any remaining issues for this intent
                for iss in i_issues:
                    if iss not in [missing_framework, missing_persistence]:
                        questions.append(self._issue_to_question(iss))
            else:
                for issue in i_issues:
                    if issue.requires_user_answer:
                        questions.append(self._issue_to_question(issue))

        return questions

    def _issue_to_question(self, issue: ClarificationIssue) -> ClarificationQuestion:
        q_id = f"q_{uuid.uuid4().hex[:8]}"
        q_type = QuestionType.SHORT_TEXT
        options = []

        if issue.issue_type == ClarificationIssueType.AMBIGUOUS_FRAMEWORK:
            q_type = QuestionType.SINGLE_SELECT
            options = issue.candidate_defaults or ["CLI", "Tkinter", "Web"]
        elif issue.issue_type == ClarificationIssueType.MISSING_PERSISTENCE_CHOICE:
            q_type = QuestionType.SINGLE_SELECT
            options = issue.candidate_defaults or ["JSON", "SQLite"]
        elif issue.issue_type == ClarificationIssueType.AMBIGUOUS_TARGET:
            q_type = QuestionType.SHORT_TEXT # Or list of files if we had them
            q_text = f"{issue.message} (You can also type 'defer' to skip this for now.)"
            return ClarificationQuestion(
                question_id=q_id,
                text=q_text,
                question_type=q_type,
                options=options,
                related_issue_ids=[issue.issue_id]
            )
        elif issue.issue_type == ClarificationIssueType.REQUEST_TOO_BROAD:
            q_type = QuestionType.BOOLEAN
            options = ["Yes, proceed", "No, let me refine"]

        return ClarificationQuestion(
            question_id=q_id,
            text=issue.message,
            question_type=q_type,
            options=options,
            related_issue_ids=[issue.issue_id]
        )

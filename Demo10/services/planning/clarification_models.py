from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

class ClarificationIssueType(Enum):
    MISSING_REQUIRED_CHOICE = "missing_required_choice"
    AMBIGUOUS_TARGET = "ambiguous_target"
    AMBIGUOUS_FRAMEWORK = "ambiguous_framework"
    AMBIGUOUS_ENTRYPOINT = "ambiguous_entrypoint"
    CONFLICTING_CONSTRAINTS = "conflicting_constraints"
    REQUEST_TOO_BROAD = "request_too_broad"
    MISSING_RUNTIME_CHOICE = "missing_runtime_choice"
    MISSING_PERSISTENCE_CHOICE = "missing_persistence_choice"
    MISSING_TEST_POLICY = "missing_test_policy"
    UNKNOWN_TARGET_ENTITY = "unknown_target_entity"

class ClarificationSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"

class ResolutionMode(Enum):
    INFER_AND_PROCEED = "infer_and_proceed"
    PROCEED_WITH_WARNING = "proceed_with_warning"
    MUST_CLARIFY = "must_clarify"
    MUST_BLOCK = "must_block"

@dataclass
class ClarificationIssue:
    issue_id: str
    issue_type: ClarificationIssueType
    severity: ClarificationSeverity
    resolution_mode: ResolutionMode
    message: str
    scope: str = "request" # e.g. "request", "intent", "step"
    related_intent_ids: List[str] = field(default_factory=list)
    field_path: Optional[str] = None
    candidate_defaults: List[str] = field(default_factory=list)
    requires_user_answer: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "issue_type": self.issue_type.value,
            "severity": self.severity.value,
            "resolution_mode": self.resolution_mode.value,
            "message": self.message,
            "scope": self.scope,
            "related_intent_ids": self.related_intent_ids,
            "field_path": self.field_path,
            "candidate_defaults": self.candidate_defaults,
            "requires_user_answer": self.requires_user_answer
        }

class QuestionType(Enum):
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    SHORT_TEXT = "short_text"
    BOOLEAN = "boolean"

@dataclass
class ClarificationQuestion:
    question_id: str
    text: str
    question_type: QuestionType
    options: List[str] = field(default_factory=list)
    related_issue_ids: List[str] = field(default_factory=list)
    suggested_answer: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_id": self.question_id,
            "text": self.text,
            "question_type": self.question_type.value,
            "options": self.options,
            "related_issue_ids": self.related_issue_ids,
            "suggested_answer": self.suggested_answer
        }

class ClarificationSessionStatus(Enum):
    NO_CLARIFICATION_NEEDED = "no_clarification_needed"
    AWAITING_USER = "awaiting_user"
    ANSWERED = "answered"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"

@dataclass
class ClarificationSession:
    session_id: str
    request_id: str
    normalized_request_id: str
    planning_skeleton_id: str
    status: ClarificationSessionStatus = ClarificationSessionStatus.NO_CLARIFICATION_NEEDED
    issues: List[ClarificationIssue] = field(default_factory=list)
    questions: List[ClarificationQuestion] = field(default_factory=list)
    answers: Dict[str, Any] = field(default_factory=dict) # question_id -> answer
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "request_id": self.request_id,
            "normalized_request_id": self.normalized_request_id,
            "planning_skeleton_id": self.planning_skeleton_id,
            "status": self.status.value,
            "issues": [i.to_dict() for i in self.issues],
            "questions": [q.to_dict() for q in self.questions],
            "answers": self.answers,
            "updated_at": self.updated_at
        }

from __future__ import annotations
from typing import List, Dict, Any, Optional
from .planning_models import NormalizedRequest, PlanningSkeleton, IntentType, ComplexityClass
from .clarification_models import ClarificationIssue, ClarificationIssueType, ClarificationSeverity, ResolutionMode
from templates.models import DraftTemplate

class ClarificationDetector:
    def detect_issues(
        self,
        normalized_request: NormalizedRequest,
        planning_skeleton: PlanningSkeleton,
        template: Optional[DraftTemplate] = None,
        session_context: Optional[Dict[str, Any]] = None
    ) -> List[ClarificationIssue]:
        issues = []

        # 1. Broad request check
        if planning_skeleton.complexity_class == ComplexityClass.TOO_BROAD:
            issues.append(ClarificationIssue(
                issue_id="issue_too_broad",
                issue_type=ClarificationIssueType.REQUEST_TOO_BROAD,
                severity=ClarificationSeverity.WARNING,
                resolution_mode=ResolutionMode.PROCEED_WITH_WARNING,
                message="The request is very broad and contains many sub-intents. Consider narrowing it down for better results."
            ))

        # 2. Intent-specific checks
        for intent in normalized_request.intents:
            # UI Intent checks
            if intent.intent_type == IntentType.ADD_UI:
                # Check if framework is specified in entities or constraints
                frameworks = ["tkinter", "web", "cli", "desktop", "flask", "django", "react", "vue", "qt"]
                found_framework = False
                for f in frameworks:
                    if any(f in e.lower() for e in intent.entities) or any(f in c.lower() for c in intent.constraints):
                        found_framework = True
                        break

                if not found_framework:
                    issues.append(ClarificationIssue(
                        issue_id=f"issue_ui_framework_{intent.intent_id}",
                        issue_type=ClarificationIssueType.AMBIGUOUS_FRAMEWORK,
                        severity=ClarificationSeverity.BLOCKING,
                        resolution_mode=ResolutionMode.MUST_CLARIFY,
                        message=f"UI framework for '{intent.summary}' is not specified. Should it be CLI, Tkinter, or Web?",
                        scope="intent",
                        related_intent_ids=[intent.intent_id],
                        candidate_defaults=["CLI", "Tkinter", "Web"]
                    ))

            # Persistence Intent checks
            if intent.intent_type == IntentType.ADD_PERSISTENCE:
                persistence_types = ["sqlite", "json", "csv", "database", "postgres", "redis"]
                found_persistence = False
                for p in persistence_types:
                    if any(p in e.lower() for e in intent.entities) or any(p in c.lower() for c in intent.constraints):
                        found_persistence = True
                        break

                if not found_persistence:
                    issues.append(ClarificationIssue(
                        issue_id=f"issue_persistence_{intent.intent_id}",
                        issue_type=ClarificationIssueType.MISSING_PERSISTENCE_CHOICE,
                        severity=ClarificationSeverity.BLOCKING,
                        resolution_mode=ResolutionMode.MUST_CLARIFY,
                        message=f"Persistence method for '{intent.summary}' is unclear. Do you want JSON file storage or SQLite?",
                        scope="intent",
                        related_intent_ids=[intent.intent_id],
                        candidate_defaults=["JSON", "SQLite"]
                    ))

            # Patching/Feature checks (target ambiguity)
            if intent.intent_type in [IntentType.FIX_BUG, IntentType.ADD_FEATURE, IntentType.REFACTOR_LOCAL]:
                if not intent.entities:
                    issues.append(ClarificationIssue(
                        issue_id=f"issue_target_{intent.intent_id}",
                        issue_type=ClarificationIssueType.AMBIGUOUS_TARGET,
                        severity=ClarificationSeverity.BLOCKING,
                        resolution_mode=ResolutionMode.MUST_CLARIFY,
                        message=f"Target file or module for '{intent.summary}' is not clearly specified.",
                        scope="intent",
                        related_intent_ids=[intent.intent_id]
                    ))

        # 3. Template-specific checks (if template provided)
        if template:
            # We could check if required parameters are missing here
            # But DraftSpecTranslator already does some of this.
            # However, Spec 038 wants this at the clarification gate.
            pass

        # 4. Inferred defaults (Info/Warning)
        # Entrypoint inference
        has_entrypoint = any("main.py" in e.lower() or "app.py" in e.lower() for e in normalized_request.entities)
        if not has_entrypoint and normalized_request.intents:
             issues.append(ClarificationIssue(
                issue_id="issue_default_entrypoint",
                issue_type=ClarificationIssueType.AMBIGUOUS_ENTRYPOINT,
                severity=ClarificationSeverity.INFO,
                resolution_mode=ResolutionMode.INFER_AND_PROCEED,
                message="No entrypoint specified. Defaulting to main.py.",
                candidate_defaults=["main.py"],
                requires_user_answer=False
            ))

        return issues

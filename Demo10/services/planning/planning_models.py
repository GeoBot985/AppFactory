from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

class IntentType(Enum):
    BUILD_COMPONENT = "build_component"
    ADD_FEATURE = "add_feature"
    FIX_BUG = "fix_bug"
    ADD_TESTS = "add_tests"
    RUN_TESTS = "run_tests"
    WIRE_INTEGRATION = "wire_integration"
    ADD_UI = "add_ui"
    ADD_PERSISTENCE = "add_persistence"
    REFACTOR_LOCAL = "refactor_local"
    UNKNOWN = "unknown"

class ComplexityClass(Enum):
    SINGLE_INTENT_SIMPLE = "single_intent_simple"
    MULTI_INTENT_LINEAR = "multi_intent_linear"
    MULTI_INTENT_CONDITIONAL = "multi_intent_conditional"
    MULTI_INTENT_AMBIGUOUS = "multi_intent_ambiguous"
    TOO_BROAD = "too_broad"

class ConditionType(Enum):
    ON_SUCCESS = "on_success"
    ALWAYS = "always"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"

@dataclass
class IntentUnit:
    intent_id: str
    intent_type: IntentType
    summary: str
    source_span: Optional[str] = None
    priority: int = 0
    entities: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    confidence: float = 1.0
    dependency_hints: List[str] = field(default_factory=list)
    ambiguities: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "intent_type": self.intent_type.value,
            "summary": self.summary,
            "source_span": self.source_span,
            "priority": self.priority,
            "entities": self.entities,
            "constraints": self.constraints,
            "confidence": self.confidence,
            "dependency_hints": self.dependency_hints,
            "ambiguities": self.ambiguities
        }

@dataclass
class NormalizedRequest:
    request_id: str
    original_text: str
    cleaned_summary: str
    action_phrases: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    explicit_constraints: List[str] = field(default_factory=list)
    unresolved_ambiguities: List[str] = field(default_factory=list)
    intents: List[IntentUnit] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "original_text": self.original_text,
            "cleaned_summary": self.cleaned_summary,
            "action_phrases": self.action_phrases,
            "entities": self.entities,
            "explicit_constraints": self.explicit_constraints,
            "unresolved_ambiguities": self.unresolved_ambiguities,
            "intents": [i.to_dict() for i in self.intents]
        }

@dataclass
class SkeletonStep:
    step_id: str
    intent_id: str
    summary: str
    template_id: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    condition: ConditionType = ConditionType.ALWAYS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "intent_id": self.intent_id,
            "summary": self.summary,
            "template_id": self.template_id,
            "depends_on": self.depends_on,
            "condition": self.condition.value
        }

@dataclass
class PlanningSkeleton:
    skeleton_id: str
    request_id: str
    steps: List[SkeletonStep] = field(default_factory=list)
    complexity_class: ComplexityClass = ComplexityClass.SINGLE_INTENT_SIMPLE
    planning_warnings: List[str] = field(default_factory=list)
    planning_confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skeleton_id": self.skeleton_id,
            "request_id": self.request_id,
            "steps": [s.to_dict() for s in self.steps],
            "complexity_class": self.complexity_class.value,
            "planning_warnings": self.planning_warnings,
            "planning_confidence": self.planning_confidence
        }

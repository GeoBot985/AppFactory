from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

class Certainty(Enum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"

class UncertaintySeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"

@dataclass
class UncertaintyRecord:
    code: str
    message: str
    severity: UncertaintySeverity
    field_path: str
    certainty: Certainty = Certainty.EXPLICIT
    suggested_resolution: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "field_path": self.field_path,
            "certainty": self.certainty.value,
            "suggested_resolution": self.suggested_resolution
        }

@dataclass
class DraftTask:
    id: str
    type: str
    path: str
    summary: str
    depends_on: List[str] = field(default_factory=list)
    certainty: Certainty = Certainty.EXPLICIT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "path": self.path,
            "summary": self.summary,
            "depends_on": self.depends_on,
            "certainty": self.certainty.value
        }

@dataclass
class DraftIntent:
    task_kind: str
    summary: str
    constraints: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_kind": self.task_kind,
            "summary": self.summary,
            "constraints": self.constraints
        }

@dataclass
class DraftTargets:
    inferred_editable_paths: List[str] = field(default_factory=list)
    inferred_readonly_context: List[str] = field(default_factory=list)
    inferred_entrypoints: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inferred_editable_paths": self.inferred_editable_paths,
            "inferred_readonly_context": self.inferred_readonly_context,
            "inferred_entrypoints": self.inferred_entrypoints
        }

@dataclass
class DraftSpec:
    draft_spec_version: int = 1
    draft_id: str = ""
    title: str = ""
    description: str = ""
    intent: DraftIntent = field(default_factory=lambda: DraftIntent("unknown", ""))
    targets: DraftTargets = field(default_factory=DraftTargets)
    tasks: List[DraftTask] = field(default_factory=list)
    policies: Dict[str, Any] = field(default_factory=lambda: {"require_tests_pass": True, "fail_fast": True})
    uncertainties: List[UncertaintyRecord] = field(default_factory=list)
    translation_notes: Dict[str, List[str]] = field(default_factory=lambda: {"assumptions": [], "unresolved_questions": []})
    origin_metadata: Dict[str, Any] = field(default_factory=lambda: {"origin_type": "freeform_translation"})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "draft_spec_version": self.draft_spec_version,
            "draft_id": self.draft_id,
            "title": self.title,
            "description": self.description,
            "intent": self.intent.to_dict(),
            "targets": self.targets.to_dict(),
            "tasks": [t.to_dict() for t in self.tasks],
            "policies": self.policies,
            "uncertainties": [u.to_dict() for u in self.uncertainties],
            "translation_notes": self.translation_notes,
            "origin_metadata": self.origin_metadata
        }

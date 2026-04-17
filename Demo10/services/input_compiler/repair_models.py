from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Literal
from .issues import CompileIssue
from .models import CompiledSpecIR

@dataclass
class RepairAction:
    action_id: str
    issue_code: str
    action_type: Literal[
        "set_field",
        "select_from_candidates",
        "remove_operation",
        "replace_operation",
        "add_missing_field"
    ]
    target_field: str
    value: Any = None
    candidates: List[Any] = field(default_factory=list)
    requires_user_input: bool = True
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "issue_code": self.issue_code,
            "action_type": self.action_type,
            "target_field": self.target_field,
            "value": self.value,
            "candidates": self.candidates,
            "requires_user_input": self.requires_user_input,
            "description": self.description
        }

@dataclass
class RepairIteration:
    iteration_id: int
    issues_before: List[CompileIssue] = field(default_factory=list)
    applied_repairs: List[RepairAction] = field(default_factory=list)
    resulting_ir: Optional[CompiledSpecIR] = None
    compile_status: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration_id": self.iteration_id,
            "issues_before": [i.to_dict() for i in self.issues_before],
            "applied_repairs": [a.to_dict() for a in self.applied_repairs],
            "resulting_ir": self.resulting_ir.to_dict() if self.resulting_ir else None,
            "compile_status": self.compile_status
        }

@dataclass
class RepairSession:
    session_id: str
    original_input: str
    iterations: List[RepairIteration] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "original_input": self.original_input,
            "iterations": [i.to_dict() for i in self.iterations]
        }

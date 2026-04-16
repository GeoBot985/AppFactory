from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
from services.task_service import Task

class CompileStatus(Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    STALE = "stale"

class DiagnosticSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

@dataclass
class CompileDiagnostic:
    severity: DiagnosticSeverity
    code: str
    message: str
    field_path: Optional[str] = None
    task_id: Optional[str] = None
    suggested_fix: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "field_path": self.field_path,
            "task_id": self.task_id,
            "suggested_fix": self.suggested_fix
        }

@dataclass
class CompileReport:
    status: CompileStatus
    errors: List[CompileDiagnostic] = field(default_factory=list)
    warnings: List[CompileDiagnostic] = field(default_factory=list)
    normalized_metadata: Dict[str, Any] = field(default_factory=dict)
    blocking_status: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "normalized_metadata": self.normalized_metadata,
            "blocking_status": self.blocking_status
        }

@dataclass
class CompiledPlan:
    plan_id: str
    tasks: List[Task]
    execution_graph: List[str] # Ordered task IDs
    policies: Dict[str, Any]
    allowed_targets: List[str]
    compile_report: CompileReport
    created_at: str
    draft_hash: str
    is_stale: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "tasks": [t.id for t in self.tasks], # Simplified for summary
            "execution_graph": self.execution_graph,
            "policies": self.policies,
            "allowed_targets": self.allowed_targets,
            "compile_report": self.compile_report.to_dict(),
            "created_at": self.created_at,
            "draft_hash": self.draft_hash,
            "is_stale": self.is_stale
        }

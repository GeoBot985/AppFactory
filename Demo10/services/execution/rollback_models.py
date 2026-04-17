from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Literal

CompensationType = Literal[
    "reversible",
    "compensatable",
    "non_reversible"
]

@dataclass
class CompensationAction:
    compensation_id: str
    source_step_id: str
    action_type: Literal[
        "delete_created_file",
        "restore_file_backup",
        "remove_generated_artifact",
        "noop_record_only"
    ]
    target: Optional[str] = None
    inputs: Dict[str, Any] = field(default_factory=dict)
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "compensation_id": self.compensation_id,
            "source_step_id": self.source_step_id,
            "action_type": self.action_type,
            "target": self.target,
            "inputs": self.inputs,
            "status": self.status,
            "error_code": self.error_code,
            "error_message": self.error_message
        }

@dataclass
class RollbackPlan:
    rollback_id: str
    run_id: str
    actions: List[CompensationAction] = field(default_factory=list)
    status: Literal[
        "pending",
        "running",
        "completed",
        "completed_with_warnings",
        "failed"
    ] = "pending"
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rollback_id": self.rollback_id,
            "run_id": self.run_id,
            "actions": [a.to_dict() for a in self.actions],
            "status": self.status,
            "issues": self.issues
        }

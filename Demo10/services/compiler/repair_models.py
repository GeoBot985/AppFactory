from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

class RepairConfidence(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class RepairStatus(Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    ABORTED = "aborted"

@dataclass
class RepairChange:
    field_path: str
    old_value: Any
    new_value: Any
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_path": self.field_path,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "description": self.description
        }

@dataclass
class CompileRepairAttempt:
    attempt_id: int
    confidence: RepairConfidence
    reason: str # e.g. "deterministic_fix", "llm_inference"
    changes: List[RepairChange] = field(default_factory=list)
    errors_fixed: List[str] = field(default_factory=list) # error codes
    status: RepairStatus = RepairStatus.PENDING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "confidence": self.confidence.value,
            "reason": self.reason,
            "changes": [c.to_dict() for c in self.changes],
            "errors_fixed": self.errors_fixed,
            "status": self.status.value
        }

@dataclass
class CompileRepairSession:
    session_id: str
    draft_id: str
    attempts: List[CompileRepairAttempt] = field(default_factory=list)
    final_status: RepairStatus = RepairStatus.PENDING
    max_attempts: int = 3

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "draft_id": self.draft_id,
            "attempts": [a.to_dict() for a in self.attempts],
            "final_status": self.final_status.value,
            "max_attempts": self.max_attempts
        }

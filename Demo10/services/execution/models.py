from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal

@dataclass
class StepResult:
    step_id: str
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)

    error_code: Optional[str] = None
    error_message: Optional[str] = None

    preconditions_passed: bool = False
    postconditions_passed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "preconditions_passed": self.preconditions_passed,
            "postconditions_passed": self.postconditions_passed
        }

@dataclass
class Run:
    run_id: str
    plan_id: str
    status: Literal["pending", "running", "completed", "failed", "partial_failure"] = "pending"
    current_step_id: Optional[str] = None
    step_results: Dict[str, StepResult] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "plan_id": self.plan_id,
            "status": self.status,
            "current_step_id": self.current_step_id,
            "step_results": {k: v.to_dict() for k, v in self.step_results.items()},
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None
        }

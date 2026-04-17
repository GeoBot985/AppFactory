from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Literal

@dataclass
class ReplayRequest:
    replay_id: str
    source_run_id: str
    mode: Literal["trace_replay", "re_execute"]
    workspace_mode: Literal["in_place", "cloned_workspace", "temp_workspace"]
    include_rollback: bool = False

@dataclass
class ReplayMismatch:
    category: Literal[
        "plan",
        "step_order",
        "step_status",
        "step_output",
        "retry_count",
        "rollback",
        "artifact"
    ]
    step_id: Optional[str]
    expected: Any
    actual: Any
    severity: Literal["warning", "error"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "step_id": self.step_id,
            "expected": self.expected,
            "actual": self.actual,
            "severity": self.severity
        }

@dataclass
class ReplayComparison:
    plan_match: bool
    step_order_match: bool
    step_count_match: bool
    status_match: bool
    outputs_match: bool
    rollback_match: bool
    mismatches: List[ReplayMismatch] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_match": self.plan_match,
            "step_order_match": self.step_order_match,
            "step_count_match": self.step_count_match,
            "status_match": self.status_match,
            "outputs_match": self.outputs_match,
            "rollback_match": self.rollback_match,
            "mismatches": [m.to_dict() for m in self.mismatches]
        }

@dataclass
class ReplayResult:
    replay_id: str
    source_run_id: str
    mode: str
    status: Literal["completed", "failed", "mismatch"]
    reproducibility_verdict: Literal[
        "exact_match",
        "structural_match",
        "outcome_match",
        "mismatch",
        "not_comparable"
    ]
    comparison: ReplayComparison

    def to_dict(self) -> Dict[str, Any]:
        return {
            "replay_id": self.replay_id,
            "source_run_id": self.source_run_id,
            "mode": self.mode,
            "status": self.status,
            "reproducibility_verdict": self.reproducibility_verdict,
            "comparison": self.comparison.to_dict()
        }

@dataclass
class EnvironmentFingerprint:
    python_version: str
    os_name: str
    working_directory: str
    app_version: Optional[str] = None
    handler_version_map: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "python_version": self.python_version,
            "os_name": self.os_name,
            "working_directory": self.working_directory,
            "app_version": self.app_version,
            "handler_version_map": self.handler_version_map
        }

from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

class CheckStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    ERROR = "error"

class Severity(Enum):
    HARD = "hard"
    SOFT = "soft"

class FinalOutcome(Enum):
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    FAILED = "FAILED"

class FailureStage(Enum):
    SPEC_FAILURE = "SPEC_FAILURE"
    PLANNER_FAILURE = "PLANNER_FAILURE"
    EDIT_FAILURE = "EDIT_FAILURE"
    STRUCTURAL_VALIDATION_FAILURE = "STRUCTURAL_VALIDATION_FAILURE"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"
    REGRESSION_FAILURE = "REGRESSION_FAILURE"
    HARNESS_FAILURE = "HARNESS_FAILURE"
    SNAPSHOT_CREATION_FAILURE = "SNAPSHOT_CREATION_FAILURE"
    EXECUTION_WORKSPACE_RESOLUTION_FAILURE = "EXECUTION_WORKSPACE_RESOLUTION_FAILURE"
    PROMOTION_CONFLICT = "PROMOTION_CONFLICT"
    PROMOTION_FAILURE = "PROMOTION_FAILURE"
    RETENTION_FAILURE = "RETENTION_FAILURE"
    FIXTURE_RESOLUTION_FAILURE = "FIXTURE_RESOLUTION_FAILURE"
    RUNTIME_PROFILE_INVALID = "RUNTIME_PROFILE_INVALID"
    RUNTIME_ENVIRONMENT_FAILURE = "RUNTIME_ENVIRONMENT_FAILURE"
    POLICY_CONTROL = "POLICY_CONTROL"
    APPROVAL_DENIED = "APPROVAL_DENIED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    PROMOTION_BLOCKED_BY_POLICY = "PROMOTION_BLOCKED_BY_POLICY"
    RISK_CLASSIFICATION_FAILURE = "RISK_CLASSIFICATION_FAILURE"

@dataclass
class CheckResult:
    check_id: str
    type: str
    severity: Severity
    status: CheckStatus
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)

@dataclass
class VerificationReport:
    checks: List[CheckResult] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)

@dataclass
class RunSummary:
    spec_id: str
    mode: str
    tasks_total: int
    tasks_applied: int
    tasks_no_op: int
    tasks_failed: int
    verification: Dict[str, int]
    regression: Dict[str, Any]
    final_status: FinalOutcome
    failure_stage: Optional[FailureStage]
    summary: str = ""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal

@dataclass
class RetryPolicy:
    max_attempts: int
    retryable_error_codes: List[str]
    delay_ms: int
    backoff_mode: Literal["none", "linear", "fixed"]
    requires_recheck: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "retryable_error_codes": self.retryable_error_codes,
            "delay_ms": self.delay_ms,
            "backoff_mode": self.backoff_mode,
            "requires_recheck": self.requires_recheck
        }

@dataclass
class StepAttempt:
    attempt_index: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    status: Literal["running", "completed", "failed"] = "running"
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    preconditions_passed: bool = False
    postconditions_passed: bool = False
    outputs: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt_index": self.attempt_index,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "status": self.status,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "preconditions_passed": self.preconditions_passed,
            "postconditions_passed": self.postconditions_passed,
            "outputs": self.outputs
        }

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

    attempts: List[StepAttempt] = field(default_factory=list)
    final_attempt_count: int = 0
    recovered_via_retry: bool = False
    retry_exhausted: bool = False

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
            "postconditions_passed": self.postconditions_passed,
            "attempts": [a.to_dict() for a in self.attempts],
            "final_attempt_count": self.final_attempt_count,
            "recovered_via_retry": self.recovered_via_retry,
            "retry_exhausted": self.retry_exhausted
        }

@dataclass
class HandlerResult:
    success: bool
    outputs: Dict[str, Any] = field(default_factory=dict)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    is_transient: Optional[bool] = None

@dataclass
class Run:
    run_id: str
    plan_id: str
    status: Literal["pending", "running", "completed", "failed", "partial_failure"] = "pending"
    current_step_id: Optional[str] = None
    step_results: Dict[str, StepResult] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: Optional[datetime] = None

    # Summary fields
    total_retries: int = 0
    recovered_steps: int = 0
    retry_exhausted_steps: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "plan_id": self.plan_id,
            "status": self.status,
            "current_step_id": self.current_step_id,
            "step_results": {k: v.to_dict() for k, v in self.step_results.items()},
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "total_retries": self.total_retries,
            "recovered_steps": self.recovered_steps,
            "retry_exhausted_steps": self.retry_exhausted_steps
        }

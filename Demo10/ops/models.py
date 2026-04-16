from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

class HealthSeverity(Enum):
    OK = "OK"
    WARN = "WARN"
    DEGRADED = "DEGRADED"
    BROKEN = "BROKEN"
    FAIL = "FAIL"

@dataclass
class DashboardSummary:
    active_queues: int = 0
    paused_queues: int = 0
    running_runs: int = 0
    approval_pending_runs: int = 0
    failed_runs_24h: int = 0
    partial_failures_24h: int = 0
    completed_runs_24h: int = 0
    blocked_promotions: int = 0
    interrupted_runs: int = 0
    failing_regression_suites: int = 0
    ledger_issues: int = 0
    banners: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "active_queues": self.active_queues,
            "paused_queues": self.paused_queues,
            "running_runs": self.running_runs,
            "approval_pending_runs": self.approval_pending_runs,
            "failed_runs_24h": self.failed_runs_24h,
            "partial_failures_24h": self.partial_failures_24h,
            "completed_runs_24h": self.completed_runs_24h,
            "blocked_promotions": self.blocked_promotions,
            "interrupted_runs": self.interrupted_runs,
            "failing_regression_suites": self.failing_regression_suites,
            "ledger_issues": self.ledger_issues,
            "banners": self.banners
        }

@dataclass
class QueueIndexEntry:
    queue_id: str
    status: str
    source_policy: str
    runtime_profile_default: str
    slots_total: int
    slots_completed: int
    slots_failed: int
    slots_pending: int
    slots_approval_pending: int
    current_slot_id: Optional[str]
    created_at: str
    updated_at: str
    age_minutes: int

    def to_dict(self):
        return self.__dict__

@dataclass
class RunIndexEntry:
    run_id: str
    queue_id: str
    slot_id: str
    spec_id: str
    state: str
    final_status: Optional[str]
    failure_stage: Optional[str]
    risk_class: Optional[str]
    policy_status: Optional[str]
    approval_status: Optional[str]
    promotion_status: Optional[str]
    runtime_profile: str
    started_at: str
    duration_seconds: Optional[float]
    last_phase: Optional[str]
    resumable_classification: Optional[str]

    def to_dict(self):
        return self.__dict__

@dataclass
class ApprovalIndexEntry:
    approval_id: str
    gate_type: str
    entity_type: str
    entity_id: str
    queue_id: str
    slot_id: str
    risk_class: str
    reason_codes: List[str]
    status: str
    requested_at: str
    age_minutes: int
    decider: Optional[str]
    decided_at: Optional[str]

    def to_dict(self):
        return self.__dict__

@dataclass
class RegressionIndexEntry:
    suite_id: str
    runtime_profile: str
    last_run_at: str
    last_status: str
    passing_cases: int
    failing_cases: int
    warning_cases: int
    environment_baseline_match_status: str
    update_baseline_history: List[str] = field(default_factory=list)

    def to_dict(self):
        return self.__dict__

@dataclass
class RecoveryIndexEntry:
    run_id: str
    queue_id: str
    last_durable_state: str
    classification: str
    action_options: List[str]
    artifact_integrity: str

    def to_dict(self):
        return self.__dict__

@dataclass
class RuntimeProfileIndexEntry:
    profile_id: str
    total_runs: int
    failed_runs: int
    drift_events: int
    timeout_counts: int
    interpreter: str

    def to_dict(self):
        return self.__dict__

@dataclass
class HealthStatus:
    status: str # OK, WARN, DEGRADED, BROKEN
    generated_at: str
    components: Dict[str, str] # e.g., "queues": "WARN"

    def to_dict(self):
        return self.__dict__

@dataclass
class TrendData:
    timestamp: str
    runs_by_status: Dict[str, int]
    failures_by_stage: Dict[str, int]
    approvals_by_decision: Dict[str, int]
    regressions_by_status: Dict[str, int]

    def to_dict(self):
        return self.__dict__

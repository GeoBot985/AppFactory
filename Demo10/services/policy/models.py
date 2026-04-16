from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime

class RiskClass(Enum):
    R0_LOW = "R0_LOW"
    R1_MODERATE = "R1_MODERATE"
    R2_HIGH = "R2_HIGH"
    R3_CRITICAL = "R3_CRITICAL"

    @property
    def rank(self) -> int:
        return {
            RiskClass.R0_LOW: 0,
            RiskClass.R1_MODERATE: 1,
            RiskClass.R2_HIGH: 2,
            RiskClass.R3_CRITICAL: 3
        }[self]

    def __ge__(self, other):
        if self.__class__ is other.__class__:
            return self.rank >= other.rank
        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.rank > other.rank
        return NotImplemented

    def __le__(self, other):
        if self.__class__ is other.__class__:
            return self.rank <= other.rank
        return NotImplemented

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.rank < other.rank
        return NotImplemented

class PolicyDecision(Enum):
    POLICY_ALLOWED = "POLICY_ALLOWED"
    POLICY_DENIED = "POLICY_DENIED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"

class PolicyDomain(Enum):
    SPEC_INTAKE = "SPEC_INTAKE"
    EXECUTION = "EXECUTION"
    PROMOTION = "PROMOTION"
    QUEUE = "QUEUE"

class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

class ApprovalGateType(Enum):
    EXECUTION = "execution"
    PROMOTION = "promotion"
    QUEUE_CONTINUATION = "queue_continuation"
    REPLAY_BASELINE = "replay_baseline"

@dataclass
class ApprovalRecord:
    approval_id: str
    gate_type: str  # execution | promotion | queue_continuation | replay_baseline
    entity_type: str # run | queue
    entity_id: str
    queue_id: str
    slot_id: str
    required_for: str
    risk_class: str
    reason_codes: List[str]
    status: str = ApprovalStatus.PENDING.value
    requested_at: str = field(default_factory=lambda: datetime.now().isoformat())
    decided_at: Optional[str] = None
    decider: Optional[str] = None
    comment: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "approval_id": self.approval_id,
            "gate_type": self.gate_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "queue_id": self.queue_id,
            "slot_id": self.slot_id,
            "required_for": self.required_for,
            "risk_class": self.risk_class,
            "reason_codes": self.reason_codes,
            "status": self.status,
            "requested_at": self.requested_at,
            "decided_at": self.decided_at,
            "decider": self.decider,
            "comment": self.comment
        }

@dataclass
class PolicyEvaluationResult:
    policy_domain: str
    entity_id: str
    risk_class: str
    decision: str
    reason_codes: List[str] = field(default_factory=list)
    matched_rules: List[str] = field(default_factory=list)
    facts: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "policy_domain": self.policy_domain,
            "entity_id": self.entity_id,
            "risk_class": self.risk_class,
            "decision": self.decision,
            "reason_codes": self.reason_codes,
            "matched_rules": self.matched_rules,
            "facts": self.facts
        }

@dataclass
class RiskAssessment:
    spec_risk: str
    task_risks: List[Dict[str, Any]]
    promotion_risk_estimate: str
    overall_risk: str

    def to_dict(self) -> dict:
        return {
            "spec_risk": self.spec_risk,
            "task_risks": self.task_risks,
            "promotion_risk_estimate": self.promotion_risk_estimate,
            "overall_risk": self.overall_risk
        }

@dataclass
class PolicyConfig:
    version: int = 1
    defaults: Dict[str, Any] = field(default_factory=lambda: {
        "unattended_max_risk": RiskClass.R1_MODERATE.value,
        "autopromote_max_risk": RiskClass.R0_LOW.value,
        "allow_promotion_on_status": ["COMPLETED"]
    })
    protected_paths: Dict[str, List[str]] = field(default_factory=lambda: {
        "high_risk": [
            "src/runtime_profiles/**",
            "src/workspace/**",
            "src/run_ledger/**",
            "src/policy/**"
        ],
        "critical": [
            "src/promotion/**",
            "src/recovery/**",
            "config/**"
        ]
    })
    command_rules: Dict[str, Any] = field(default_factory=lambda: {
        "denied_executables": ["rm", "del", "format"],
        "shell_string_commands_require_approval": True,
        "runtime_override_timeout_above_seconds_requires_approval": 300
    })
    execution_rules: Dict[str, Any] = field(default_factory=lambda: {
        "delete_block_requires_approval": True,
        "delete_file_requires_approval": True,
        "max_auto_changed_files": 5,
        "bulk_replace_above_lines_requires_approval": 100
    })
    promotion_rules: Dict[str, Any] = field(default_factory=lambda: {
        "allow_auto_promotion_statuses": ["COMPLETED"],
        "warnings_require_approval": True,
        "deletion_requires_approval": True,
        "protected_paths_require_approval": True
    })
    queue_rules: Dict[str, Any] = field(default_factory=lambda: {
        "on_approval_required": "pause",
        "on_policy_denied": "fail_slot",
        "allow_low_risk_slots_to_continue_after_denial": False
    })

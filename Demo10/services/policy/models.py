from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime

Environment = Literal["dev", "staging", "prod"]

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
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"
    # Legacy support
    POLICY_ALLOWED = "allow"
    POLICY_DENIED = "block"
    APPROVAL_REQUIRED = "warn"

class PolicyDomain(Enum):
    COMPILE = "COMPILE"
    PREVIEW = "PREVIEW"
    EXECUTION = "EXECUTION"
    TASK = "TASK"
    RERUN = "RERUN"
    RESTORE = "RESTORE"
    PROMOTION = "PROMOTION"
    SPEC_INTAKE = "SPEC_INTAKE"
    APPLY = "APPLY"

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
    risk_class: Optional[str] = None
    decision: str = ""
    reasons: List[str] = field(default_factory=list)
    policy_rules_triggered: List[str] = field(default_factory=list)
    # Compatibility aliases
    reason_codes: List[str] = field(default_factory=list)
    matched_rules: List[str] = field(default_factory=list)
    facts: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "policy_domain": self.policy_domain,
            "entity_id": self.entity_id,
            "risk_class": self.risk_class,
            "decision": self.decision,
            "reasons": self.reasons,
            "policy_rules_triggered": self.policy_rules_triggered,
            "facts": self.facts,
            "timestamp": self.timestamp
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
class ScopePolicy:
    max_edit_files: int = 5
    max_new_files: int = 3
    allowed_directories: List[str] = field(default_factory=lambda: ["*"])
    cross_module_limits: Optional[int] = None

@dataclass
class RiskPolicy:
    allow_high_risk: bool = True
    require_approval_above: str = RiskClass.R1_MODERATE.value
    denied_executables: List[str] = field(default_factory=lambda: ["rm", "del", "format"])
    protected_paths: Dict[str, List[str]] = field(default_factory=lambda: {
        "high_risk": ["src/policy/**", "Demo10/services/policy/**", "Demo10/services/run_ledger/**"],
        "critical": ["config/**", "Demo10/workspace/**", "Demo10/services/compiled_runtime/**"]
    })

@dataclass
class ExecutionPolicy:
    require_tests_pass: bool = True
    max_attempts_per_task: int = 3
    allow_auto_run: bool = True
    fail_fast: bool = True

@dataclass
class RestorePolicy:
    allow_restore_on_drift: bool = True
    allow_restore_with_mismatch: bool = False

@dataclass
class RerunPolicy:
    max_rerun_depth: int = 5
    allowed_rerun_range: str = "all" # all | task_only

@dataclass
class PromotionCandidate:
    candidate_id: str
    source_environment: Environment
    target_environment: Environment
    system_version: str
    verification_suite_id: str
    verification_result_id: str
    timestamp: datetime

@dataclass
class PromotionDecision:
    candidate_id: str
    decision: Literal["approved", "approved_with_warnings", "rejected", "approved_with_override"]
    reasons: List[str]
    policy_snapshot: Dict[str, Any]
    evaluated_at: datetime

@dataclass
class EnvironmentPolicy:
    allow_warn: bool
    allow_not_comparable: bool
    required_verdict: Literal["pass", "pass_with_warnings"]
    blocked_drift_categories: List[str]
    max_failures: int
    require_exact_match: bool

@dataclass
class PromotionPolicy:
    policy_id: str
    environment_rules: Dict[Environment, EnvironmentPolicy]

@dataclass
class PromotionHistory:
    system_version: str
    environments_reached: List[Environment]
    decisions: List[PromotionDecision]

@dataclass
class PolicyConfig:
    version: int = 1
    scope: ScopePolicy = field(default_factory=ScopePolicy)
    risk: RiskPolicy = field(default_factory=RiskPolicy)
    execution: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    restore: RestorePolicy = field(default_factory=RestorePolicy)
    rerun: RerunPolicy = field(default_factory=RerunPolicy)
    promotion: Optional[PromotionPolicy] = None

    # Legacy mappings for backward compatibility during transition
    @property
    def defaults(self):
        return {
            "unattended_max_risk": self.risk.require_approval_above,
            "autopromote_max_risk": RiskClass.R0_LOW.value,
        }

    @property
    def command_rules(self):
        return {
            "denied_executables": self.risk.denied_executables,
            "shell_string_commands_require_approval": True,
            "runtime_override_timeout_above_seconds_requires_approval": 300
        }

    @property
    def execution_rules(self):
        return {
            "delete_block_requires_approval": True,
            "delete_file_requires_approval": True,
            "max_auto_changed_files": self.scope.max_edit_files,
            "bulk_replace_above_lines_requires_approval": 100
        }

    @property
    def promotion_rules(self):
        return {
            "allow_auto_promotion_statuses": ["COMPLETED"],
            "warnings_require_approval": True,
            "deletion_requires_approval": True,
            "protected_paths_require_approval": True
        }

    @property
    def protected_paths(self):
        return self.risk.protected_paths

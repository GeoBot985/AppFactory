from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class GoalSignature:
    signature_id: str
    operation_types: List[str]
    targets: List[str]
    constraints: List[str]
    intent_tokens: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signature_id": self.signature_id,
            "operation_types": self.operation_types,
            "targets": self.targets,
            "constraints": self.constraints,
            "intent_tokens": self.intent_tokens
        }

@dataclass
class RoutingRule:
    rule_id: str
    goal_pattern: Dict[str, Any]      # predicates over GoalSignature
    macro_name: str
    min_version: Optional[str] = None
    priority: int = 0
    required_contracts: List[str] = field(default_factory=list)
    blocked_conditions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "goal_pattern": self.goal_pattern,
            "macro_name": self.macro_name,
            "min_version": self.min_version,
            "priority": self.priority,
            "required_contracts": self.required_contracts,
            "blocked_conditions": self.blocked_conditions
        }

@dataclass
class MacroMatch:
    macro_id: str
    version: str
    rule_id: str
    score: int                     # deterministic score
    reasons: List[str] = field(default_factory=list)
    blocked_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "macro_id": self.macro_id,
            "version": self.version,
            "rule_id": self.rule_id,
            "score": self.score,
            "reasons": self.reasons,
            "blocked_reasons": self.blocked_reasons
        }

@dataclass
class RoutingDecision:
    decision_id: str
    goal_signature_id: str
    selected_macros: List[str]     # macro_ids (ordered)
    fallback_used: bool = False
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "goal_signature_id": self.goal_signature_id,
            "selected_macros": self.selected_macros,
            "fallback_used": self.fallback_used,
            "reasons": self.reasons
        }

from typing import Dict, Any, List, Optional
from .models import (
    RiskClass,
    PolicyDecision,
    PolicyDomain,
    PolicyConfig,
    PolicyEvaluationResult,
    RiskAssessment
)
from .rules import (
    PolicyRule,
    MaxEditFilesRule,
    MaxNewFilesRule,
    RiskLevelRule,
    DeniedExecutableRule,
    RetryLimitRule,
    RestoreDriftRule,
    RerunDepthRule
)
import logging
from pathlib import Path
from .logging import PolicyLogService

logger = logging.getLogger(__name__)

class PolicyEngine:
    def __init__(self, config: PolicyConfig, project_root: Optional[Path] = None):
        self.config = config
        self.log_service = PolicyLogService(project_root or Path("."))
        self.rules: List[PolicyRule] = [
            MaxEditFilesRule(),
            MaxNewFilesRule(),
            RiskLevelRule(),
            DeniedExecutableRule(),
            RetryLimitRule(),
            RestoreDriftRule(),
            RerunDepthRule()
        ]

    def evaluate(self, domain: PolicyDomain, entity_id: str, context: Dict[str, Any]) -> PolicyEvaluationResult:
        decisions: List[tuple[PolicyDecision, str, str]] = []

        for rule in self.rules:
            decision, reason = rule.evaluate(domain, context, self.config)
            if decision != PolicyDecision.ALLOW:
                decisions.append((decision, reason, rule.__class__.__name__))

        # Decision aggregation
        # Block > Warn > Allow
        final_decision = PolicyDecision.ALLOW
        reasons = []
        matched_rules = []

        if any(d[0] == PolicyDecision.BLOCK for d in decisions):
            final_decision = PolicyDecision.BLOCK
        elif any(d[0] == PolicyDecision.WARN for d in decisions):
            final_decision = PolicyDecision.WARN

        for decision, reason, rule_name in decisions:
            if decision == final_decision or (final_decision == PolicyDecision.BLOCK and decision == PolicyDecision.WARN):
                reasons.append(reason)
                matched_rules.append(rule_name)

        result = PolicyEvaluationResult(
            policy_domain=domain.value,
            entity_id=entity_id,
            decision=final_decision.value,
            risk_class=context.get("risk_class"),
            reasons=reasons,
            policy_rules_triggered=matched_rules,
            facts=context
        )

        self.log_decision(result)
        return result

    def log_decision(self, result: PolicyEvaluationResult):
        self.log_service.log_decision(result)
        logger.info(f"Policy Decision: {result.policy_domain} for {result.entity_id} -> {result.decision}. Reasons: {result.reasons}")

# Maintain legacy PolicyEvaluator for gradual migration
from .evaluator import PolicyEvaluator as LegacyEvaluator

class PolicyEvaluator(LegacyEvaluator):
    def __init__(self, config: PolicyConfig, project_root: Optional[Path] = None):
        super().__init__(config)
        self.engine = PolicyEngine(config, project_root)

    def evaluate_pre_execution(self, entity_id: str, assessment: RiskAssessment) -> PolicyEvaluationResult:
        # Map assessment to context for new engine
        context = {
            "risk_class": assessment.overall_risk,
            "commands": [tr.get("target", "") for tr in assessment.task_risks] # Rough mapping
        }
        # In actual tasks, task_risks might not have target, but we'll improve this integration

        # Use new engine for Preview (Spec 031 gate)
        result = self.engine.evaluate(PolicyDomain.PREVIEW, entity_id, context)

        # Fallback/merge with legacy for now if needed, but Spec 033 says "no implicit safety logic scattered"
        return result

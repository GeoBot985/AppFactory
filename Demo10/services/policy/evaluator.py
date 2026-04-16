from typing import Dict, Any, List, Optional
from .models import (
    RiskClass,
    PolicyDecision,
    PolicyDomain,
    PolicyConfig,
    PolicyEvaluationResult,
    RiskAssessment
)

class PolicyEvaluator:
    def __init__(self, config: PolicyConfig):
        self.config = config

    def evaluate_pre_execution(self, entity_id: str, assessment: RiskAssessment) -> PolicyEvaluationResult:
        domain = PolicyDomain.SPEC_INTAKE.value
        risk = RiskClass(assessment.overall_risk)
        reasons = []
        matched_rules = []
        decision = PolicyDecision.POLICY_ALLOWED

        # Hard deny check (Requirement 15)
        for task_risk in assessment.task_risks:
            if task_risk["risk"] == RiskClass.R3_CRITICAL.value:
                for reason in task_risk["reasons"]:
                    if "denied executable" in reason.lower():
                        decision = PolicyDecision.POLICY_DENIED
                        reasons.append("DENIED_EXECUTABLE")
                        matched_rules.append("command_rules.denied_executables")
                        return PolicyEvaluationResult(domain, entity_id, risk.value, decision.value, reasons, matched_rules)

        # Unattended max risk check (Requirement 4)
        unattended_max = RiskClass(self.config.defaults.get("unattended_max_risk", RiskClass.R1_MODERATE.value))
        if risk > unattended_max:
             decision = PolicyDecision.APPROVAL_REQUIRED
             reasons.append("UNATTENDED_RISK_THRESHOLD_EXCEEDED")
             matched_rules.append("defaults.unattended_max_risk")

        # Specific execution rules (Requirement 16)
        if True: # Evaluate specific rules even if already approval_required to gather all reason codes
            for task_risk in assessment.task_risks:
                for reason in task_risk["reasons"]:
                    if "delete_block" in reason.lower() and self.config.execution_rules.get("delete_block_requires_approval"):
                        decision = PolicyDecision.APPROVAL_REQUIRED
                        reasons.append("DELETE_BLOCK_OPERATION")
                        matched_rules.append("execution_rules.delete_block_requires_approval")

                    if "DELETE task" in reason and self.config.execution_rules.get("delete_file_requires_approval"):
                        decision = PolicyDecision.APPROVAL_REQUIRED
                        reasons.append("FILE_DELETE_OPERATION")
                        matched_rules.append("execution_rules.delete_file_requires_approval")

                    if "Shell string command" in reason and self.config.command_rules.get("shell_string_commands_require_approval"):
                        decision = PolicyDecision.APPROVAL_REQUIRED
                        reasons.append("SHELL_STRING_COMMAND")
                        matched_rules.append("command_rules.shell_string_commands_require_approval")

        return PolicyEvaluationResult(
            policy_domain=domain,
            entity_id=entity_id,
            risk_class=risk.value,
            decision=decision.value,
            reason_codes=list(set(reasons)),
            matched_rules=list(set(matched_rules))
        )

    def evaluate_pre_promotion(self, entity_id: str, risk: RiskClass, facts: Dict[str, Any]) -> PolicyEvaluationResult:
        domain = PolicyDomain.PROMOTION.value
        reasons = []
        matched_rules = []
        decision = PolicyDecision.POLICY_ALLOWED

        # Hard deny rules (Requirement 15)
        status = facts.get("final_status")
        if status in {"FAILED", "PARTIAL_FAILURE"}:
            decision = PolicyDecision.POLICY_DENIED
            reasons.append("UNPROMOTABLE_STATUS")
            matched_rules.append("promotion_rules.allow_auto_promotion_statuses")
            return PolicyEvaluationResult(domain, entity_id, risk.value, decision.value, reasons, matched_rules)

        # Auto-promote max risk check
        auto_max = RiskClass(self.config.defaults.get("autopromote_max_risk", RiskClass.R0_LOW.value))
        if risk > auto_max:
            decision = PolicyDecision.APPROVAL_REQUIRED
            reasons.append("PROMOTION_RISK_ABOVE_AUTO_THRESHOLD")
            matched_rules.append("defaults.autopromote_max_risk")

        # Specific promotion rules (Requirement 16)
        if status == "COMPLETED_WITH_WARNINGS" and self.config.promotion_rules.get("warnings_require_approval"):
            decision = PolicyDecision.APPROVAL_REQUIRED
            reasons.append("FINAL_STATUS_COMPLETED_WITH_WARNINGS")
            matched_rules.append("promotion_rules.warnings_require_approval")

        if facts.get("contains_deletion") and self.config.promotion_rules.get("deletion_requires_approval"):
            decision = PolicyDecision.APPROVAL_REQUIRED
            reasons.append("DELETION_PRESENT")
            matched_rules.append("promotion_rules.deletion_requires_approval")

        if (facts.get("touches_protected_path") or facts.get("touches_critical_path")) and self.config.promotion_rules.get("protected_paths_require_approval"):
            decision = PolicyDecision.APPROVAL_REQUIRED
            reasons.append("PROTECTED_PATH_TOUCHED")
            matched_rules.append("promotion_rules.protected_paths_require_approval")

        return PolicyEvaluationResult(
            policy_domain=domain,
            entity_id=entity_id,
            risk_class=risk.value,
            decision=decision.value,
            reason_codes=list(set(reasons)),
            matched_rules=list(set(matched_rules)),
            facts=facts
        )

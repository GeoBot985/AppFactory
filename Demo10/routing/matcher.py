from typing import List, Optional
from .models import GoalSignature, RoutingRule, MacroMatch
from .rules import RuleManager
from Demo10.macros.models import WorkflowMacro, MacroLibrary

class RoutingMatcher:
    def __init__(self, rule_manager: RuleManager):
        self.rule_manager = rule_manager

    def find_matches(self, sig: GoalSignature, macros: List[WorkflowMacro], rules: List[RoutingRule]) -> List[MacroMatch]:
        matches = []

        for rule in rules:
            if self.rule_manager.evaluate_rule(rule, sig):
                # Rule matches, now check eligible macros
                for macro in macros:
                    if macro.name == rule.macro_name:
                        match = self._evaluate_eligibility(macro, rule, sig)
                        if match:
                            matches.append(match)

        return matches

    def _evaluate_eligibility(self, macro: WorkflowMacro, rule: RoutingRule, sig: GoalSignature) -> Optional[MacroMatch]:
        reasons = ["rule_matched"]
        blocked_reasons = []

        # verification_status == "verified"
        if macro.verification_status != "verified":
            blocked_reasons.append(f"macro_not_verified: {macro.verification_status}")

        # macro is active (handled by checking active versions usually, but let's check status)
        if macro.verification_status == "deprecated":
            blocked_reasons.append("macro_deprecated")

        # version >= min_version
        if rule.min_version:
            if not self._is_version_ge(macro.version, rule.min_version):
                blocked_reasons.append(f"version_too_low: {macro.version} < {rule.min_version}")

        # SafetyContract satisfied
        if "workspace_bound" in rule.required_contracts:
            if not macro.safety_contract.workspace_bound:
                blocked_reasons.append("contract_mismatch: workspace_bound")

        if "preserves_rollback_behavior" in rule.required_contracts:
            if not macro.safety_contract.preserves_rollback_behavior:
                blocked_reasons.append("contract_mismatch: preserves_rollback_behavior")

        # blocked_conditions (placeholder for v1)
        for cond in rule.blocked_conditions:
            if cond == "destructive" and any(op in ["delete_file", "format_disk"] for op in sig.operation_types):
                 blocked_reasons.append(f"blocked_condition: {cond}")

        # In v1, we only return a match if not blocked.
        # But for scoring/audit we might want to keep blocked ones?
        # Spec says "A macro is eligible only if...".

        if blocked_reasons:
            return None # Or return MacroMatch with score 0? Spec implies filtering first.

        return MacroMatch(
            macro_id=macro.macro_id,
            version=macro.version,
            rule_id=rule.rule_id,
            score=0, # to be set by Scorer
            reasons=reasons,
            blocked_reasons=blocked_reasons
        )

    def _is_version_ge(self, v1: str, v2: str) -> bool:
        # Simplistic v1, v2, ... comparison
        try:
            num1 = int(v1.lstrip('v'))
            num2 = int(v2.lstrip('v'))
            return num1 >= num2
        except:
            return v1 >= v2

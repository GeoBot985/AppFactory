from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from .models import PolicyDecision, PolicyDomain, PolicyConfig, RiskClass

class PolicyRule(ABC):
    @abstractmethod
    def evaluate(self, domain: PolicyDomain, context: Dict[str, Any], config: PolicyConfig) -> tuple[PolicyDecision, Optional[str]]:
        pass

class MaxEditFilesRule(PolicyRule):
    def evaluate(self, domain: PolicyDomain, context: Dict[str, Any], config: PolicyConfig) -> tuple[PolicyDecision, Optional[str]]:
        if domain != PolicyDomain.COMPILE:
            return PolicyDecision.ALLOW, None

        files_touched = context.get("files_touched", 0)
        if files_touched > config.scope.max_edit_files:
            return PolicyDecision.BLOCK, f"max_edit_files_exceeded: {files_touched} > {config.scope.max_edit_files}"
        return PolicyDecision.ALLOW, None

class MaxNewFilesRule(PolicyRule):
    def evaluate(self, domain: PolicyDomain, context: Dict[str, Any], config: PolicyConfig) -> tuple[PolicyDecision, Optional[str]]:
        if domain != PolicyDomain.COMPILE:
            return PolicyDecision.ALLOW, None

        new_files = context.get("new_files", 0)
        if new_files > config.scope.max_new_files:
            return PolicyDecision.BLOCK, f"max_new_files_exceeded: {new_files} > {config.scope.max_new_files}"
        return PolicyDecision.ALLOW, None

class RiskLevelRule(PolicyRule):
    def evaluate(self, domain: PolicyDomain, context: Dict[str, Any], config: PolicyConfig) -> tuple[PolicyDecision, Optional[str]]:
        if domain != PolicyDomain.PREVIEW:
            return PolicyDecision.ALLOW, None

        risk_class_str = context.get("risk_class")
        if not risk_class_str:
            return PolicyDecision.ALLOW, None

        risk_class = RiskClass(risk_class_str)

        # Check allow_high_risk
        if not config.risk.allow_high_risk and risk_class >= RiskClass.R2_HIGH:
            return PolicyDecision.BLOCK, f"high_risk_not_allowed: {risk_class.value}"

        # Check require_approval_above
        threshold = RiskClass(config.risk.require_approval_above)
        if risk_class > threshold:
            return PolicyDecision.WARN, f"risk_level_requires_approval: {risk_class.value} > {threshold.value}"

        return PolicyDecision.ALLOW, None

class DeniedExecutableRule(PolicyRule):
    def evaluate(self, domain: PolicyDomain, context: Dict[str, Any], config: PolicyConfig) -> tuple[PolicyDecision, Optional[str]]:
        if domain not in [PolicyDomain.PREVIEW, PolicyDomain.TASK]:
            return PolicyDecision.ALLOW, None

        commands = context.get("commands", [])
        for cmd in commands:
            for denied in config.risk.denied_executables:
                if denied in cmd:
                    return PolicyDecision.BLOCK, f"denied_executable_detected: {denied} in {cmd}"
        return PolicyDecision.ALLOW, None

class RetryLimitRule(PolicyRule):
    def evaluate(self, domain: PolicyDomain, context: Dict[str, Any], config: PolicyConfig) -> tuple[PolicyDecision, Optional[str]]:
        if domain != PolicyDomain.TASK:
            return PolicyDecision.ALLOW, None

        attempts = context.get("attempts", 0)
        if attempts >= config.execution.max_attempts_per_task:
            return PolicyDecision.BLOCK, f"max_attempts_per_task_exceeded: {attempts} >= {config.execution.max_attempts_per_task}"
        return PolicyDecision.ALLOW, None

class RestoreDriftRule(PolicyRule):
    def evaluate(self, domain: PolicyDomain, context: Dict[str, Any], config: PolicyConfig) -> tuple[PolicyDecision, Optional[str]]:
        if domain != PolicyDomain.RESTORE:
            return PolicyDecision.ALLOW, None

        has_drift = context.get("has_drift", False)
        if has_drift and not config.restore.allow_restore_on_drift:
            return PolicyDecision.BLOCK, "restore_blocked_on_drift"
        elif has_drift:
            return PolicyDecision.WARN, "restore_with_drift_warning"
        return PolicyDecision.ALLOW, None

class RerunDepthRule(PolicyRule):
    def evaluate(self, domain: PolicyDomain, context: Dict[str, Any], config: PolicyConfig) -> tuple[PolicyDecision, Optional[str]]:
        if domain != PolicyDomain.RERUN:
            return PolicyDecision.ALLOW, None

        depth = context.get("rerun_depth", 0)
        if depth > config.rerun.max_rerun_depth:
            return PolicyDecision.BLOCK, f"max_rerun_depth_exceeded: {depth} > {config.rerun.max_rerun_depth}"
        return PolicyDecision.ALLOW, None

from __future__ import annotations
import time
from typing import Optional
from .impact_model import ImpactPreview, ApprovalState, ApprovalStatus, RiskLevel
from services.policy.engine import PolicyEngine
from services.policy.models import PolicyConfig, PolicyDomain, PolicyDecision, RiskClass

class ApprovalController:
    def __init__(self, policy_config: Optional[PolicyConfig] = None):
        self.policy_engine = PolicyEngine(policy_config or PolicyConfig())

    def evaluate(self, preview: ImpactPreview) -> ApprovalState:
        state = ApprovalState()

        # Map ImpactPreview RiskLevel to Policy RiskClass
        risk_map = {
            RiskLevel.LOW: RiskClass.R0_LOW,
            RiskLevel.MEDIUM: RiskClass.R1_MODERATE,
            RiskLevel.HIGH: RiskClass.R2_HIGH,
        }

        policy_context = {
            "risk_class": risk_map.get(preview.risk_level, RiskClass.R0_LOW).value,
            "risk_reasons": preview.risk_reasons,
            "total_files": preview.summary.total_files,
            "files_deleted": preview.summary.files_deleted
        }

        policy_result = self.policy_engine.evaluate(PolicyDomain.PREVIEW, "preview_id", policy_context)

        if policy_result.decision == PolicyDecision.ALLOW.value:
            state.approval_required = False
            state.status = ApprovalStatus.AUTO_APPROVED
            state.source = "system"
            state.reason = "Policy allowed: Low risk plan auto-approved"
        elif policy_result.decision == PolicyDecision.BLOCK.value:
            state.approval_required = True
            state.status = ApprovalStatus.REJECTED
            state.source = "policy_engine"
            state.reason = f"Blocked by policy: {', '.join(policy_result.reasons)}"
        else: # WARN -> Approval Required
            state.approval_required = True
            state.status = ApprovalStatus.PENDING
            state.source = "system"
            state.reason = f"Policy requires approval: {', '.join(policy_result.reasons)}"

        state.timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        return state

    def approve(self, state: ApprovalState, user: str, reason: str = "") -> None:
        state.status = ApprovalStatus.APPROVED
        state.source = user
        state.reason = reason
        state.timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")

    def reject(self, state: ApprovalState, user: str, reason: str = "") -> None:
        state.status = ApprovalStatus.REJECTED
        state.source = user
        state.reason = reason
        state.timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")

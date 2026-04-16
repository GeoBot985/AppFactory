from __future__ import annotations
import time
from typing import Optional
from .impact_model import ImpactPreview, ApprovalState, ApprovalStatus, RiskLevel

class ApprovalController:
    def __init__(self, auto_approve_low_risk: bool = True):
        self.auto_approve_low_risk = auto_approve_low_risk

    def evaluate(self, preview: ImpactPreview) -> ApprovalState:
        state = ApprovalState()

        if self.auto_approve_low_risk and preview.risk_level == RiskLevel.LOW:
            state.approval_required = False
            state.status = ApprovalStatus.AUTO_APPROVED
            state.source = "system"
            state.reason = "Low risk plan auto-approved"
        else:
            state.approval_required = True
            state.status = ApprovalStatus.PENDING
            state.source = "system"
            state.reason = f"Manual approval required for {preview.risk_level.value} risk plan"

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

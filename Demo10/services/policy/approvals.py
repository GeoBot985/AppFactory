import json
import uuid
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime
from .models import ApprovalRecord, ApprovalStatus, PolicyEvaluationResult

class ApprovalService:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.approvals_file = project_root / "runtime_data" / "policy" / "approvals.json"
        self.approvals_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_approvals()

    def _load_approvals(self):
        if self.approvals_file.exists():
            try:
                with self.approvals_file.open("r") as f:
                    data = json.load(f)
                    self.approvals = {k: ApprovalRecord(**v) for k, v in data.items()}
            except:
                self.approvals = {}
        else:
            self.approvals = {}

    def _save_approvals(self):
        with self.approvals_file.open("w") as f:
            json.dump({k: v.to_dict() for k, v in self.approvals.items()}, f, indent=2)

    def create_approval_request(
        self,
        gate_type: str,
        entity_type: str,
        entity_id: str,
        queue_id: str,
        slot_id: str,
        evaluation: PolicyEvaluationResult
    ) -> ApprovalRecord:
        approval_id = f"appr_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:4]}"

        required_for = "EXECUTE_TASKS" if gate_type == "execution" else "PROMOTE_CHANGES"

        record = ApprovalRecord(
            approval_id=approval_id,
            gate_type=gate_type,
            entity_type=entity_type,
            entity_id=entity_id,
            queue_id=queue_id,
            slot_id=slot_id,
            required_for=required_for,
            risk_class=evaluation.risk_class,
            reason_codes=evaluation.reason_codes
        )

        self.approvals[approval_id] = record
        self._save_approvals()
        return record

    def get_approval(self, approval_id: str) -> Optional[ApprovalRecord]:
        return self.approvals.get(approval_id)

    def list_pending(self) -> List[ApprovalRecord]:
        return [a for a in self.approvals.values() if a.status == ApprovalStatus.PENDING.value]

    def approve(self, approval_id: str, decider: str, comment: str = "") -> bool:
        record = self.get_approval(approval_id)
        if record and record.status == ApprovalStatus.PENDING.value:
            record.status = ApprovalStatus.APPROVED.value
            record.decider = decider
            record.decided_at = datetime.now().isoformat()
            record.comment = comment
            self._save_approvals()
            return True
        return False

    def deny(self, approval_id: str, decider: str, comment: str = "") -> bool:
        record = self.get_approval(approval_id)
        if record and record.status == ApprovalStatus.PENDING.value:
            record.status = ApprovalStatus.DENIED.value
            record.decider = decider
            record.decided_at = datetime.now().isoformat()
            record.comment = comment
            self._save_approvals()
            return True
        return False

    def find_latest_for_entity(self, entity_id: str, gate_type: str) -> Optional[ApprovalRecord]:
        matches = [a for a in self.approvals.values() if a.entity_id == entity_id and a.gate_type == gate_type]
        if not matches:
            return None
        matches.sort(key=lambda x: x.requested_at, reverse=True)
        return matches[0]

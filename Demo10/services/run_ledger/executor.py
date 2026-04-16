import json
import shutil
from pathlib import Path
from typing import Any, Optional, Dict
from datetime import datetime
import uuid
from .models import RunMetadata, RunState

class ResumeService:
    def __init__(self, storage_root: Path, ledger_service: Any):
        self.storage_root = storage_root
        self.ledger_service = ledger_service

    def prepare_resume(self, run_id: str) -> Optional[RunMetadata]:
        metadata = self.ledger_service.get_run_metadata(run_id)
        if not metadata:
            return None

        # Validate eligibility
        if metadata.state in {RunState.COMPLETED, RunState.FAILED}:
            # Should not resume terminal states unless explicit
            return None

        if not metadata.execution_workspace or not Path(metadata.execution_workspace).exists():
            return None

        return metadata

class ReplayService:
    def __init__(self, storage_root: Path, ledger_service: Any, audit_log_service: Any):
        self.storage_root = storage_root
        self.ledger_service = ledger_service
        self.audit_log_service = audit_log_service

    def create_replay_run(self, original_run_id: str) -> Optional[RunMetadata]:
        original = self.ledger_service.get_run_metadata(original_run_id)
        if not original:
            return None

        replay_id = f"replay_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"

        replay_metadata = RunMetadata(
            run_id=replay_id,
            spec_id=original.spec_id,
            queue_id=original.queue_id,
            slot_id=original.slot_id,
            state=RunState.CREATED,
            execution_mode=original.execution_mode,
            runtime_profile=original.runtime_profile,
            source_policy=original.source_policy,
            replay_of_run_id=original_run_id
        )

        return replay_metadata

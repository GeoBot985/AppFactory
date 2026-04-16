from __future__ import annotations
import shutil
import json
import uuid
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from datetime import datetime
from .models import WorkspaceSnapshot, RestoreRun, SnapshotFileEntry, RestoreRequest
from .fingerprints import FingerprintService

class RestoreValidator:
    def __init__(self, fingerprint_service: FingerprintService):
        self.fingerprint_service = fingerprint_service

    def validate_restore_request(self, snapshot: WorkspaceSnapshot, workspace_root: Path) -> Tuple[str, List[str]]:
        if snapshot.workspace_root != str(workspace_root.resolve()):
            return "restore_blocked_workspace_mismatch", ["Workspace root mismatch"]

        # For beta, we don't block yet, but we should detect drift
        # Detect if current workspace has changed since the snapshot
        return "restore_allowed", []

    def build_restore_preview(self, snapshot: WorkspaceSnapshot, workspace_root: Path) -> Dict[str, any]:
        current_fingerprint = self.fingerprint_service.compute_fingerprint(workspace_root)

        snapshot_files = {e.relative_path: e.content_hash for e in snapshot.manifest}
        current_files = current_fingerprint.entries

        to_restore = [] # Files in snapshot that differ or are missing in workspace
        to_remove = []  # Files in workspace that are NOT in snapshot
        drifted = []    # Files currently in workspace that differ from snapshot baseline

        all_paths = set(snapshot_files.keys()) | set(current_files.keys())

        for path in all_paths:
            snap_hash = snapshot_files.get(path)
            curr_hash = current_files.get(path)

            if snap_hash and not curr_hash:
                to_restore.append(path)
            elif curr_hash and not snap_hash:
                to_remove.append(path)
            elif snap_hash != curr_hash:
                to_restore.append(path)
                drifted.append(path)

        return {
            "snapshot_id": snapshot.snapshot_id,
            "source_run_id": snapshot.source_run_id,
            "source_compiled_plan_id": snapshot.source_compiled_plan_id,
            "files_to_restore": sorted(to_restore),
            "files_to_remove": sorted(to_remove),
            "files_drifted": sorted(drifted),
            "warnings": []
        }

class RestoreController:
    def __init__(self, snapshot_service, ledger_service):
        self.snapshot_service = snapshot_service
        self.ledger_service = ledger_service
        self.fingerprint_service = snapshot_service.fingerprint_service
        self.validator = RestoreValidator(self.fingerprint_service)

    def execute_restore(self, request: RestoreRequest) -> RestoreRun:
        snapshot = self.snapshot_service.get_snapshot(request.snapshot_id)
        if not snapshot:
            raise ValueError(f"Snapshot {request.snapshot_id} not found")

        workspace_root = Path(request.target_workspace)

        restore_run = RestoreRun(
            restore_run_id=f"rest_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}",
            snapshot_id=request.snapshot_id,
            workspace_root=str(workspace_root),
            requested_by=request.requested_by,
            reason=request.reason,
            base_run_id=snapshot.source_run_id,
            started_at=datetime.now().isoformat(),
            status="running"
        )

        if self.ledger_service:
            self.ledger_service.record_event(
                entity_type="restore",
                entity_id=restore_run.restore_run_id,
                event_type="restore_started",
                new_state="running",
                payload=restore_run.to_dict()
            )

        try:
            # 1. Build preview to know what to do
            preview = self.validator.build_restore_preview(snapshot, workspace_root)

            # 2. Remove files not in snapshot
            for rel_path in preview["files_to_remove"]:
                target = workspace_root / rel_path
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                restore_run.files_removed_count += 1

            # 3. Restore/Replace files from snapshot
            snapshot_dir = self.snapshot_service.storage_root / snapshot.snapshot_id
            for entry in snapshot.manifest:
                # Only restore if it was in the to_restore list (differs or missing)
                if entry.relative_path in preview["files_to_restore"]:
                    source_in_snap = snapshot_dir / entry.storage_ref
                    target_in_ws = workspace_root / entry.relative_path

                    target_in_ws.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_in_snap, target_in_ws)
                    restore_run.files_restored_count += 1

            # 4. Verify
            verification_ok = self.verify_restored_workspace(snapshot, workspace_root)
            restore_run.verification_status = "verified" if verification_ok else "failed_verification"
            restore_run.status = "completed"

        except Exception as e:
            restore_run.status = "failed"
            restore_run.errors.append(str(e))

        restore_run.completed_at = datetime.now().isoformat()

        # Record in ledger if available
        if self.ledger_service:
            self.ledger_service.record_event(
                entity_type="restore",
                entity_id=restore_run.restore_run_id,
                event_type="restore_completed",
                new_state=restore_run.status,
                payload=restore_run.to_dict()
            )

        return restore_run

    def verify_restored_workspace(self, snapshot: WorkspaceSnapshot, workspace_root: Path) -> bool:
        current_fingerprint = self.fingerprint_service.compute_fingerprint(workspace_root)

        snapshot_files = {e.relative_path: e.content_hash for e in snapshot.manifest}
        current_files = current_fingerprint.entries

        # Check all snapshot files are present and match hash
        for rel_path, snap_hash in snapshot_files.items():
            if current_files.get(rel_path) != snap_hash:
                return False

        # Check no extra files in current_files
        if set(current_files.keys()) != set(snapshot_files.keys()):
            return False

        return True

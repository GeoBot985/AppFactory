import os
from pathlib import Path
from typing import Dict, Any, Callable
from services.execution.rollback_models import CompensationAction
from services.execution.snapshots import SnapshotManager

class CompensationHandlers:
    def __init__(self, workspace_root: Path, run_id: str):
        self.workspace_root = workspace_root
        self.run_id = run_id
        self.snapshot_manager = SnapshotManager(workspace_root, run_id)

    def get_handler(self, action_type: str) -> Callable[[CompensationAction], None]:
        handlers = {
            "delete_created_file": self.delete_created_file,
            "restore_file_backup": self.restore_file_backup,
            "remove_generated_artifact": self.remove_generated_artifact,
            "noop_record_only": self.noop_record_only
        }
        return handlers.get(action_type, self.not_implemented_handler)

    def delete_created_file(self, action: CompensationAction):
        if not action.target:
            raise ValueError("ROLLBACK_TARGET_MISSING: No target for delete_created_file")

        # Security: ensure within workspace
        full_path = (self.workspace_root / action.target).resolve()
        if not str(full_path).startswith(str(self.workspace_root.resolve())):
            raise RuntimeError("WORKSPACE_BOUNDARY_VIOLATION: Attempted to delete file outside workspace")

        # only delete if marked created_by_run=true
        if not action.inputs.get("created_by_run"):
            # Technically we should skip or record only, but the engine should have filtered this.
            # If we are here, we expect it to be true.
            return

        if full_path.exists():
            os.remove(full_path)

        if full_path.exists():
            raise RuntimeError("ROLLBACK_VERIFICATION_FAILED: File still exists after deletion attempt")

    def restore_file_backup(self, action: CompensationAction):
        if not action.target:
            raise ValueError("ROLLBACK_TARGET_MISSING: No target for restore_file_backup")

        snapshot_path = action.inputs.get("snapshot_path")
        if not snapshot_path:
            raise ValueError("SNAPSHOT_MISSING: No snapshot path provided for restoration")

        success = self.snapshot_manager.restore_snapshot(snapshot_path, action.target)
        if not success:
            raise RuntimeError("COMPENSATION_FAILED: Failed to restore snapshot")

        # Verify checksum if provided
        expected_checksum = action.inputs.get("checksum")
        if expected_checksum:
            actual_checksum = self.snapshot_manager.get_checksum(action.target)
            if actual_checksum != expected_checksum:
                raise RuntimeError(f"ROLLBACK_VERIFICATION_FAILED: Checksum mismatch after restoration. Expected {expected_checksum}, got {actual_checksum}")

    def remove_generated_artifact(self, action: CompensationAction):
        # Similar to delete_created_file for now
        self.delete_created_file(action)

    def noop_record_only(self, action: CompensationAction):
        pass

    def not_implemented_handler(self, action: CompensationAction):
        raise NotImplementedError(f"Handler for {action.action_type} not implemented")

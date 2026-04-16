import shutil
import json
from pathlib import Path
from typing import List, Set, Tuple
from .models import SnapshotManifest, PromotionReport, PromotionStatus, WorkspaceFingerprint
from .fingerprints import FingerprintService

class PromotionService:
    def __init__(self, fingerprint_service: FingerprintService):
        self.fingerprint_service = fingerprint_service

    def detect_changes(self, source_fingerprint: WorkspaceFingerprint, execution_workspace: Path) -> Tuple[List[str], List[str], List[str]]:
        """Returns (created, modified, deleted) relative paths."""
        current_fingerprint = self.fingerprint_service.compute_fingerprint(execution_workspace)

        source_files = set(source_fingerprint.entries.keys())
        current_files = set(current_fingerprint.entries.keys())

        created = sorted(list(current_files - source_files))
        deleted = sorted(list(source_files - current_files))

        modified = []
        for path in source_files.intersection(current_files):
            if source_fingerprint.entries[path] != current_fingerprint.entries[path]:
                modified.append(path)

        return created, sorted(modified), deleted

    def promote(self, manifest: SnapshotManifest, execution_workspace: Path, target_workspace: Path) -> PromotionReport:
        created, modified, deleted = self.detect_changes(manifest.source_fingerprint, execution_workspace)

        if not created and not modified and not deleted:
            return PromotionReport(
                promotion_status=PromotionStatus.SKIPPED,
                reason="No changes detected in execution workspace",
                target_workspace=str(target_workspace.resolve())
            )

        try:
            # Apply changes to canonical workspace
            for rel_path in created + modified:
                source_file = execution_workspace / rel_path
                target_file = target_workspace / rel_path
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, target_file)

            for rel_path in deleted:
                target_file = target_workspace / rel_path
                if target_file.exists():
                    target_file.unlink()

            report = PromotionReport(
                promotion_status=PromotionStatus.APPLIED,
                reason="Changes promoted successfully",
                files_created=created,
                files_modified=modified,
                files_deleted=deleted,
                target_workspace=str(target_workspace.resolve())
            )
        except Exception as e:
            report = PromotionReport(
                promotion_status=PromotionStatus.FAILED,
                reason=f"Promotion failed: {str(e)}",
                target_workspace=str(target_workspace.resolve())
            )

        return report

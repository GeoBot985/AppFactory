from pathlib import Path
from typing import List
from .models import SnapshotManifest, ConflictReport, ConflictEntry, PromotionStatus
from .fingerprints import FingerprintService

class ConflictService:
    def __init__(self, fingerprint_service: FingerprintService):
        self.fingerprint_service = fingerprint_service

    def check_drift(self, manifest: SnapshotManifest, canonical_workspace: Path, files_to_promote: List[str]) -> ConflictReport:
        """
        Checks if the files in canonical_workspace that are about to be promoted
        have changed since the snapshot was taken.
        """
        # Re-compute fingerprint of canonical for relevant files only
        # Actually, let's just compute a full fingerprint for simplicity for now,
        # but only compare the ones we care about.
        current_canonical_fingerprint = self.fingerprint_service.compute_fingerprint(canonical_workspace)

        conflicts = []
        for rel_path in files_to_promote:
            source_hash = manifest.source_fingerprint.entries.get(rel_path)
            canonical_hash = current_canonical_fingerprint.entries.get(rel_path)

            # If it didn't exist in source but exists in canonical now, it's a conflict if we are trying to create/modify it?
            # Actually, if it's in files_to_promote, we are trying to write to it.
            # If it's different from what we thought was the base, it's a drift.

            if source_hash != canonical_hash:
                conflicts.append(ConflictEntry(
                    path=rel_path,
                    source_snapshot_hash=source_hash or "None (new file)",
                    current_canonical_hash=canonical_hash or "None (deleted)"
                ))

        if conflicts:
            return ConflictReport(
                promotion_status=PromotionStatus.BLOCKED,
                reason="PROMOTION_CONFLICT",
                conflicts=conflicts
            )

        return ConflictReport(
            promotion_status=PromotionStatus.APPLIED, # Not actually applied yet, but safe to do so
            reason="No drift detected",
            conflicts=[]
        )

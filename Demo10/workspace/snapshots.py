import shutil
import json
from pathlib import Path
from typing import List, Optional
from .models import SnapshotManifest, ExecutionMode
from .fingerprints import FingerprintService

class SnapshotService:
    def __init__(self, fingerprint_service: FingerprintService):
        self.fingerprint_service = fingerprint_service

    def create_execution_snapshot(
        self,
        run_id: str,
        spec_id: str,
        source_workspace: Path,
        execution_root: Path,
        mode: ExecutionMode = ExecutionMode.PROMOTE_ON_SUCCESS,
        ignore_patterns: Optional[List[str]] = None
    ) -> SnapshotManifest:
        if ignore_patterns is None:
            ignore_patterns = [".git", "__pycache__", "runs", "regression_runs"]

        # Create execution workspace directory
        execution_workspace = execution_root / "execution_workspace"
        execution_workspace.mkdir(parents=True, exist_ok=True)

        # Copy canonical workspace to execution workspace
        self._copy_workspace(source_workspace, execution_workspace, ignore_patterns)

        # Compute fingerprint of source
        fingerprint = self.fingerprint_service.compute_fingerprint(source_workspace, ignore_patterns)

        manifest = SnapshotManifest(
            run_id=run_id,
            spec_id=spec_id,
            source_workspace=str(source_workspace.resolve()),
            execution_workspace=str(execution_workspace.resolve()),
            mode=mode.value,
            source_fingerprint=fingerprint
        )

        # Save manifest
        manifest_path = execution_root / "snapshot_manifest.json"
        with open(manifest_path, "w") as f:
            # We need a custom serializer or convert dataclass to dict
            manifest_dict = self._manifest_to_dict(manifest)
            json.dump(manifest_dict, f, indent=2)

        return manifest

    def _copy_workspace(self, source: Path, target: Path, ignore_patterns: List[str]):
        for item in source.iterdir():
            if item.name in ignore_patterns:
                continue

            if item.is_dir():
                shutil.copytree(item, target / item.name, ignore=shutil.ignore_patterns(*ignore_patterns), dirs_exist_ok=True)
            else:
                shutil.copy2(item, target / item.name)

    def _manifest_to_dict(self, manifest: SnapshotManifest) -> dict:
        return {
            "run_id": manifest.run_id,
            "spec_id": manifest.spec_id,
            "source_workspace": manifest.source_workspace,
            "execution_workspace": manifest.execution_workspace,
            "mode": manifest.mode,
            "created_at": manifest.created_at,
            "source_fingerprint": {
                "file_count": manifest.source_fingerprint.file_count,
                "summary_hash": manifest.source_fingerprint.summary_hash,
                "entries": manifest.source_fingerprint.entries,
                "created_at": manifest.source_fingerprint.created_at
            }
        }

import shutil
import json
from pathlib import Path
from typing import List, Optional
from .models import SnapshotManifest, ExecutionMode, WorkspaceSnapshot, SnapshotFileEntry
from .fingerprints import FingerprintService
from datetime import datetime
import uuid

class SnapshotService:
    def __init__(self, fingerprint_service: FingerprintService, storage_root: Optional[Path] = None):
        self.fingerprint_service = fingerprint_service
        self.storage_root = storage_root or Path.cwd() / "runtime_data" / "snapshots"
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def capture_baseline_snapshot(
        self,
        workspace_root: Path,
        run_id: str,
        compiled_plan_id: str,
        ignore_patterns: Optional[List[str]] = None
    ) -> WorkspaceSnapshot:
        if ignore_patterns is None:
            ignore_patterns = [".git", "__pycache__", "runs", "regression_runs", "runtime_data", "node_modules", "venv", ".venv"]

        snapshot_id = f"snap_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
        snapshot_dir = self.storage_root / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # 1. Compute fingerprint/manifest
        fingerprint = self.fingerprint_service.compute_fingerprint(workspace_root, ignore_patterns)

        manifest_entries = []
        for rel_path, file_hash in fingerprint.entries.items():
            source_file = workspace_root / rel_path
            # For beta, we copy the file to snapshot storage
            target_file = snapshot_dir / "files" / rel_path
            target_file.parent.mkdir(parents=True, exist_ok=True)

            is_binary = False
            try:
                # Basic binary detection
                with open(source_file, 'rb') as f:
                    chunk = f.read(1024)
                    if b'\0' in chunk:
                        is_binary = True
            except: pass

            shutil.copy2(source_file, target_file)

            manifest_entries.append(SnapshotFileEntry(
                relative_path=rel_path,
                exists=True,
                size=source_file.stat().st_size,
                content_hash=file_hash,
                is_binary=is_binary,
                storage_ref=str(target_file.relative_to(snapshot_dir))
            ))

        snapshot = WorkspaceSnapshot(
            snapshot_id=snapshot_id,
            workspace_root=str(workspace_root.resolve()),
            created_at=datetime.now().isoformat(),
            source_run_id=run_id,
            source_compiled_plan_id=compiled_plan_id,
            file_count=len(manifest_entries),
            excluded_count=0, # TODO: improve tracking of excluded files
            storage_mode="full_copy",
            status="active",
            manifest=manifest_entries
        )

        # Save snapshot metadata
        with open(snapshot_dir / "snapshot.json", "w") as f:
            json.dump(snapshot.to_dict(), f, indent=2)

        # 2. Enforce retention policy
        self.prune_snapshots(max_snapshots=10)

        return snapshot

    def prune_snapshots(self, max_snapshots: int = 10):
        """Retains the most recent N snapshots and prunes older ones."""
        if not self.storage_root.exists():
            return

        snapshots = []
        for snap_dir in self.storage_root.iterdir():
            if snap_dir.is_dir() and (snap_dir / "snapshot.json").exists():
                try:
                    with (snap_dir / "snapshot.json").open("r") as f:
                        data = json.load(f)
                        snapshots.append((data.get("created_at", ""), snap_dir))
                except: pass

        # Sort by creation time descending
        snapshots.sort(key=lambda x: x[0], reverse=True)

        # Keep the top N
        to_prune = snapshots[max_snapshots:]
        for created_at, snap_dir in to_prune:
            try:
                shutil.rmtree(snap_dir)
            except: pass

    def get_snapshot(self, snapshot_id: str) -> Optional[WorkspaceSnapshot]:
        snapshot_path = self.storage_root / snapshot_id / "snapshot.json"
        if not snapshot_path.exists():
            return None

        with open(snapshot_path, "r") as f:
            data = json.load(f)

        manifest_data = data.pop("manifest", [])
        snapshot = WorkspaceSnapshot(**data)
        snapshot.manifest = [SnapshotFileEntry(**e) for e in manifest_data]
        return snapshot

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
        manifest.manifest_path = str(manifest_path.resolve())
        with open(manifest_path, "w") as f:
            json.dump(manifest.to_dict(), f, indent=2)

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
        return manifest.to_dict()

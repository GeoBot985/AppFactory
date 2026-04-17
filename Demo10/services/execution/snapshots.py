import shutil
from pathlib import Path
from typing import Optional
import hashlib

class SnapshotManager:
    def __init__(self, workspace_root: Path, run_id: str):
        self.workspace_root = workspace_root
        self.run_id = run_id
        self.snapshots_dir = workspace_root / "runtime_data" / "runs" / run_id / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_file = self.snapshots_dir / "manifest.json"
        self.manifest = {}
        if self.manifest_file.exists():
            import json
            with open(self.manifest_file, "r") as f:
                self.manifest = json.load(f)

    def _save_manifest(self):
        import json
        with open(self.manifest_file, "w") as f:
            json.dump(self.manifest, f, indent=2)

    def capture_snapshot(self, target_path: str) -> Optional[str]:
        full_path = self.workspace_root / target_path
        if not full_path.exists():
            return None

        # Use hash of target path as snapshot filename to avoid path issues
        snapshot_id = hashlib.md5(target_path.encode()).hexdigest()
        snapshot_path = self.snapshots_dir / f"{snapshot_id}.snapshot"

        shutil.copy2(full_path, snapshot_path)

        rel_snapshot_path = str(snapshot_path.relative_to(self.workspace_root))
        self.manifest[snapshot_id] = {
            "original_path": target_path,
            "snapshot_path": rel_snapshot_path,
            "captured_at": str(hashlib.md5(str(snapshot_path).encode()).hexdigest()) # dummy timestamp/id
        }
        self._save_manifest()

        return rel_snapshot_path

    def restore_snapshot(self, snapshot_rel_path: str, target_path: str) -> bool:
        snapshot_path = self.workspace_root / snapshot_rel_path
        full_target_path = self.workspace_root / target_path

        if not snapshot_path.exists():
            return False

        full_target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snapshot_path, full_target_path)
        return True

    def get_checksum(self, path: str) -> Optional[str]:
        full_path = self.workspace_root / path
        if not full_path.exists():
            return None

        hasher = hashlib.sha256()
        with open(full_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

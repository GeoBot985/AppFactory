import json
import shutil
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from .models import GoldenRunMetadata

class GoldenStore:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.golden_runs_dir = workspace_root / "runtime_data" / "golden_runs"
        self.runs_dir = workspace_root / "runtime_data" / "runs"
        self.golden_runs_dir.mkdir(parents=True, exist_ok=True)

    def create_golden_run(self, source_run_id: str, notes: Optional[str] = None) -> str:
        source_dir = self.runs_dir / source_run_id
        if not source_dir.exists():
            raise FileNotFoundError(f"Source run {source_run_id} not found in {self.runs_dir}")

        golden_run_id = f"golden_{source_run_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        target_dir = self.golden_runs_dir / golden_run_id
        target_dir.mkdir(parents=True)

        # 1. Copy core artifacts
        with open(source_dir / "run.json", "r") as f:
            run_data = json.load(f)

        plan_id = run_data["plan_id"]

        # Copy the run directory
        shutil.copytree(source_dir, target_dir / "run_artifacts")

        # Copy execution plan
        plan_file = self.workspace_root / "runtime_data" / "execution_plans" / f"{plan_id}.json"
        if plan_file.exists():
            shutil.copy(plan_file, target_dir / "plan.json")
            with open(plan_file, "r") as f:
                plan_data = json.load(f)
                ir_ref = plan_data["ir_ref"]
                # Copy compiled IR
                ir_file = self.workspace_root / "runtime_data" / "compiler_runs" / f"{ir_ref}.json"
                if ir_file.exists():
                    shutil.copy(ir_file, target_dir / "ir.json")

        # 2. Capture checksums
        checksums = self._generate_checksums(target_dir)
        with open(target_dir / "checksums.json", "w") as f:
            json.dump(checksums, f, indent=2)

        # 3. Create metadata
        metadata = GoldenRunMetadata(
            golden_run_id=golden_run_id,
            source_run_id=source_run_id,
            created_at=datetime.now().isoformat(),
            system_version="1.0.0",
            notes=notes
        )

        with open(target_dir / "metadata.json", "w") as f:
            json.dump(self._to_dict(metadata), f, indent=2)

        return golden_run_id

    def verify_integrity(self, golden_run_id: str) -> bool:
        """Verifies the integrity of a golden run using checksums."""
        golden_dir = self.golden_runs_dir / golden_run_id
        if not golden_dir.exists():
            return False

        checksum_file = golden_dir / "checksums.json"
        if not checksum_file.exists():
            return False

        with open(checksum_file, "r") as f:
            expected_checksums = json.load(f)

        actual_checksums = self._generate_checksums(golden_dir)

        for path, expected in expected_checksums.items():
            if actual_checksums.get(path) != expected:
                print(f"Integrity check failed for {path}")
                return False

        return True

    def load_metadata(self, golden_run_id: str) -> GoldenRunMetadata:
        meta_file = self.golden_runs_dir / golden_run_id / "metadata.json"
        with open(meta_file, "r") as f:
            data = json.load(f)
        return GoldenRunMetadata(**data)

    def list_golden_runs(self) -> List[str]:
        return [d.name for d in self.golden_runs_dir.iterdir() if d.is_dir()]

    def _generate_checksums(self, golden_dir: Path) -> Dict[str, str]:
        checksums = {}
        # We only checksum files in the root of golden_dir and run_artifacts recursively
        # But we skip checksums.json itself and metadata.json

        for file in golden_dir.rglob("*"):
            if file.is_file():
                rel_path = str(file.relative_to(golden_dir))
                if rel_path in ["checksums.json", "metadata.json"]:
                    continue
                checksums[rel_path] = self._calculate_sha256(file)
        return checksums

    def _calculate_sha256(self, filepath: Path) -> str:
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _to_dict(self, obj: Any) -> Dict[str, Any]:
        from dataclasses import asdict, is_dataclass
        if is_dataclass(obj):
            return asdict(obj)
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "__dict__"):
            return {k: self._to_dict(v) for k, v in obj.__dict__.items()}
        if isinstance(obj, list):
            return [self._to_dict(i) for i in obj]
        if isinstance(obj, dict):
            return {k: self._to_dict(v) for k, v in obj.items()}
        return obj

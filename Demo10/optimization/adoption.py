import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from .models import OptimizedPlanVariant, OptimizationCandidate
from .safety import SafetyVerifier
from .materializer import OptimizationMaterializer
from .candidates import CandidateGenerator

class OptimizationAdopter:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.storage_path = workspace_root / "runtime_data" / "optimization"
        self.adopted_path = self.storage_path / "adopted_optimizations.json"

        self.safety_verifier = SafetyVerifier()
        self.materializer = OptimizationMaterializer(workspace_root)
        self.candidate_generator = CandidateGenerator(self.storage_path)

    def verify_variant(self, variant_id: str) -> bool:
        variant = self.materializer.get_variant(variant_id)
        if not variant:
            return False

        # In a real system, we would run the verification harness here
        # For Demo10, we simulate a successful verification if all candidates are safe
        candidates = self.candidate_generator.load_candidates()
        variant_candidates = [c for c in candidates if c.candidate_id in variant.optimization_candidate_ids]

        for cand in variant_candidates:
            if not self.safety_verifier.verify_safety(cand):
                self.materializer.update_variant_status(variant_id, "failed")
                return False

        self.materializer.update_variant_status(variant_id, "passed")
        return True

    def adopt_variant(self, variant_id: str) -> bool:
        variant = self.materializer.get_variant(variant_id)
        if not variant or variant.verification_status != "passed":
            return False

        # Record adoption
        self._record_adoption(variant)

        # Update candidate statuses
        for cand_id in variant.optimization_candidate_ids:
            self.candidate_generator.update_candidate_status(cand_id, "adopted")

        return True

    def _record_adoption(self, variant: OptimizedPlanVariant):
        if not self.adopted_path.exists():
            data = {"adopted_optimizations": []}
        else:
            with open(self.adopted_path, "r") as f:
                data = json.load(f)

        record = {
            "variant_id": variant.variant_id,
            "source_plan_id": variant.source_plan_id,
            "candidate_ids": variant.optimization_candidate_ids,
            "adopted_at": datetime.now().isoformat()
        }
        data["adopted_optimizations"].append(record)

        with open(self.adopted_path, "w") as f:
            json.dump(data, f, indent=2)

    def get_adopted_optimizations(self) -> List[Dict[str, Any]]:
        if not self.adopted_path.exists():
            return []
        with open(self.adopted_path, "r") as f:
            data = json.load(f)
            return data.get("adopted_optimizations", [])

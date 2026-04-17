import uuid
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from .models import (
    MacroPromotionCandidate,
    WorkflowMacro,
    MacroInputContract,
    MacroOutputContract,
    MacroSafetyContract,
    MacroRollbackContract
)
from Demo10.optimization.models import WorkflowFragment
from Demo10.optimization.analyzer import OptimizationAnalyzer

class MacroPromotionEngine:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.macros_dir = workspace_root / "runtime_data" / "macros"
        self.candidates_path = self.macros_dir / "promotion_candidates.json"
        self.macros_dir.mkdir(parents=True, exist_ok=True)

        self.optimization_analyzer = OptimizationAnalyzer(workspace_root)

    def promote_fragment_to_macro(
        self,
        source_fragment_id: str,
        proposed_name: str,
        proposed_version: str = "v1"
    ) -> MacroPromotionCandidate:
        # 1. Load fragment
        fragments = self.optimization_analyzer.list_fragments()
        fragment = next((f for f in fragments if f.fragment_id == source_fragment_id), None)

        if not fragment:
            raise ValueError(f"Fragment not found: {source_fragment_id}")

        # 2. Check eligibility
        is_eligible, reasons = self._check_eligibility(fragment)
        if not is_eligible:
            candidate = MacroPromotionCandidate(
                candidate_id=f"mcand_{uuid.uuid4().hex[:8]}",
                source_fragment_id=source_fragment_id,
                proposed_name=proposed_name,
                proposed_version=proposed_version,
                status="rejected",
                contracts={"eligibility_reasons": reasons}
            )
            self._save_candidate(candidate)
            return candidate

        # 3. Create candidate
        # Derive contracts from fragment
        input_contract = MacroInputContract(
            required_inputs=list(fragment.input_contract.keys())
        )
        output_contract = MacroOutputContract(
            produced_outputs=list(fragment.output_contract.keys())
        )

        candidate = MacroPromotionCandidate(
            candidate_id=f"mcand_{uuid.uuid4().hex[:8]}",
            source_fragment_id=source_fragment_id,
            proposed_name=proposed_name,
            proposed_version=proposed_version,
            contracts={
                "input_contract": vars(input_contract),
                "output_contract": vars(output_contract),
                "safety_contract": vars(MacroSafetyContract()),
                "rollback_contract": vars(MacroRollbackContract())
            },
            status="proposed"
        )

        self._save_candidate(candidate)
        return candidate

    def _check_eligibility(self, fragment: WorkflowFragment) -> tuple[bool, List[str]]:
        reasons = []

        # Rule: observed in at least 3 trusted successful runs
        if len(fragment.source_plan_ids) < 3:
            reasons.append(f"Stability threshold not met: observed in {len(fragment.source_plan_ids)} runs, required 3")

        # Rule: inputs are explicit and parameterizable
        if not fragment.input_contract:
            reasons.append("Input contract is empty")

        return len(reasons) == 0, reasons

    def _save_candidate(self, candidate: MacroPromotionCandidate):
        candidates = self.list_candidates()
        # Update if exists, else append
        existing = next((c for c in candidates if c.candidate_id == candidate.candidate_id), None)
        if existing:
            candidates.remove(existing)

        candidates.append(candidate)

        data = [self._candidate_to_dict(c) for c in candidates]
        with open(self.candidates_path, "w") as f:
            json.dump(data, f, indent=2)

    def _candidate_to_dict(self, c: MacroPromotionCandidate) -> Dict[str, Any]:
        return {
            "candidate_id": c.candidate_id,
            "source_fragment_id": c.source_fragment_id,
            "source_variant_id": c.source_variant_id,
            "proposed_name": c.proposed_name,
            "proposed_version": c.proposed_version,
            "contracts": c.contracts,
            "status": c.status
        }

    def list_candidates(self, status: Optional[str] = None) -> List[MacroPromotionCandidate]:
        if not self.candidates_path.exists():
            return []
        with open(self.candidates_path, "r") as f:
            data = json.load(f)
            candidates = [MacroPromotionCandidate(**d) for d in data]
            if status:
                candidates = [c for c in candidates if c.status == status]
            return candidates

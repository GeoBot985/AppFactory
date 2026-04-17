import uuid
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from .models import OptimizationCandidate, OptimizedPlanVariant
from ..services.planner.models import ExecutionPlan

class OptimizationMaterializer:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.storage_path = workspace_root / "runtime_data" / "optimization"
        self.variants_path = self.storage_path / "variants.json"
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def materialize_optimized_variant(self, candidate_ids: List[str], source_plan_id: str) -> OptimizedPlanVariant:
        # 1. Load source plan
        source_plan = self._load_plan(source_plan_id)

        # 2. Load candidates
        candidates = self._load_candidates(candidate_ids)

        # 3. Apply transformations
        optimized_plan_dict = source_plan.to_dict()
        for cand in candidates:
            optimized_plan_dict = self._apply_optimization(optimized_plan_dict, cand)

        # 4. Create variant
        variant = OptimizedPlanVariant(
            variant_id=f"var_{uuid.uuid4().hex[:8]}",
            source_plan_id=source_plan_id,
            optimization_candidate_ids=candidate_ids,
            execution_plan=optimized_plan_dict,
            verification_status="pending"
        )

        self._save_variant(variant)
        return variant

    def _apply_optimization(self, plan_dict: Dict[str, Any], candidate: OptimizationCandidate) -> Dict[str, Any]:
        steps = plan_dict["steps"]
        if candidate.optimization_type in ["duplicate_elimination", "io_collapse", "validation_collapse"]:
            # Remove original steps
            for sid in candidate.original_steps:
                if sid in steps:
                    removed_step_deps = steps[sid]["dependencies"]

                    # Update dependencies of steps that depend on this one
                    dependents = []
                    for other_sid, other_step in steps.items():
                        if sid in other_step["dependencies"]:
                            other_step["dependencies"].remove(sid)
                            # Inherit dependencies of the removed step
                            other_step["dependencies"].extend(removed_step_deps)
                            other_step["dependencies"] = list(set(other_step["dependencies"]))
                            dependents.append(other_sid)

                    # Update root steps
                    if sid in plan_dict["root_steps"]:
                        plan_dict["root_steps"].remove(sid)
                        # If the removed step was a root, its dependents might now be roots
                        # (only if they have no other dependencies)
                        for dep_sid in dependents:
                            if not steps[dep_sid]["dependencies"]:
                                plan_dict["root_steps"].append(dep_sid)
                        plan_dict["root_steps"] = list(set(plan_dict["root_steps"]))

                    # Update terminal steps
                    if sid in plan_dict["terminal_steps"]:
                        plan_dict["terminal_steps"].remove(sid)
                        # If the removed step was terminal, its predecessors might now be terminals
                        # (if no other step depends on them)
                        for pred_sid in removed_step_deps:
                            is_still_pred = False
                            for s in steps.values():
                                if pred_sid in s["dependencies"]:
                                    is_still_pred = True
                                    break
                            if not is_still_pred:
                                plan_dict["terminal_steps"].append(pred_sid)
                        plan_dict["terminal_steps"] = list(set(plan_dict["terminal_steps"]))

                    del steps[sid]

        # In v1, we don't handle complex step addition yet
        return plan_dict

    def _load_plan(self, plan_id: str) -> ExecutionPlan:
        # Re-use analyzer's logic or implement here
        from .analyzer import OptimizationAnalyzer
        analyzer = OptimizationAnalyzer(self.workspace_root)
        path = self.workspace_root / "runtime_data" / "execution_plans" / f"{plan_id}.json"
        return analyzer._load_plan(path)

    def _load_candidates(self, candidate_ids: List[str]) -> List[OptimizationCandidate]:
        from .candidates import CandidateGenerator
        generator = CandidateGenerator(self.storage_path)
        all_candidates = generator.load_candidates()
        return [c for c in all_candidates if c.candidate_id in candidate_ids]

    def _save_variant(self, variant: OptimizedPlanVariant):
        if not self.variants_path.exists():
            existing = []
        else:
            with open(self.variants_path, "r") as f:
                existing = json.load(f)

        existing.append(self._variant_to_dict(variant))
        with open(self.variants_path, "w") as f:
            json.dump(existing, f, indent=2)

    def _variant_to_dict(self, v: OptimizedPlanVariant) -> Dict[str, Any]:
        return {
            "variant_id": v.variant_id,
            "source_plan_id": v.source_plan_id,
            "optimization_candidate_ids": v.optimization_candidate_ids,
            "execution_plan": v.execution_plan,
            "verification_status": v.verification_status
        }

    def get_variant(self, variant_id: str) -> Optional[OptimizedPlanVariant]:
        if not self.variants_path.exists():
            return None
        with open(self.variants_path, "r") as f:
            data = json.load(f)
            for d in data:
                if d["variant_id"] == variant_id:
                    return OptimizedPlanVariant(**d)
        return None

    def update_variant_status(self, variant_id: str, status: str):
        if not self.variants_path.exists():
            return
        with open(self.variants_path, "r") as f:
            data = json.load(f)

        for d in data:
            if d["variant_id"] == variant_id:
                d["verification_status"] = status
                break

        with open(self.variants_path, "w") as f:
            json.dump(data, f, indent=2)

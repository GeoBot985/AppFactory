import json
from pathlib import Path
from typing import List, Optional
from .fragments import FragmentExtractor
from .candidates import CandidateGenerator
from .models import OptimizationCandidate, WorkflowFragment
from ..services.planner.models import ExecutionPlan

class OptimizationAnalyzer:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.storage_path = workspace_root / "runtime_data" / "optimization"
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.fragment_extractor = FragmentExtractor(self.storage_path)
        self.candidate_generator = CandidateGenerator(self.storage_path)

    def analyze_for_optimization(
        self,
        plan_ids: Optional[List[str]] = None,
        run_ids: Optional[List[str]] = None
    ) -> List[OptimizationCandidate]:
        # 1. Load plans
        plans = self._load_plans(plan_ids)
        if not plans:
            return []

        # 2. Extract fragments
        fragments = self.fragment_extractor.extract_fragments(plans)

        # 3. Generate candidates for each plan
        all_candidates = []
        for plan in plans:
            candidates = self.candidate_generator.generate_candidates(plan, fragments)
            all_candidates.extend(candidates)

        return all_candidates

    def _load_plans(self, plan_ids: Optional[List[str]]) -> List[ExecutionPlan]:
        plans_dir = self.workspace_root / "runtime_data" / "execution_plans"
        if not plans_dir.exists():
            return []

        loaded = []
        if plan_ids:
            for pid in plan_ids:
                path = plans_dir / f"{pid}.json"
                if path.exists():
                    loaded.append(self._load_plan(path))
        else:
            # Load recent plans
            for path in sorted(plans_dir.glob("*.json"), reverse=True)[:10]:
                loaded.append(self._load_plan(path))

        return loaded

    def _load_plan(self, path: Path) -> ExecutionPlan:
        with open(path, "r") as f:
            data = json.load(f)
            # Reconstruct ExecutionPlan object
            # Note: In a real implementation, we'd use a proper deserializer
            from ..services.planner.models import Step, StepContract
            steps = {}
            for sid, sdata in data.get("steps", {}).items():
                contract_data = sdata.pop("contract", {})
                contract = StepContract(**contract_data)
                steps[sid] = Step(contract=contract, **sdata)

            plan = ExecutionPlan(
                plan_id=data["plan_id"],
                ir_ref=data["ir_ref"],
                steps=steps,
                root_steps=data["root_steps"],
                terminal_steps=data["terminal_steps"],
                status=data["status"],
                created_at=data["created_at"]
            )
            return plan

    def list_fragments(self) -> List[WorkflowFragment]:
        return self.fragment_extractor.load_fragments()

    def list_candidates(self, status: Optional[str] = None) -> List[OptimizationCandidate]:
        return self.candidate_generator.load_candidates(status)

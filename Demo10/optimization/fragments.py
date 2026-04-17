import hashlib
import json
from typing import List, Dict, Any
from pathlib import Path
from .models import WorkflowFragment
from ..services.planner.models import ExecutionPlan, Step

class FragmentExtractor:
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.fragments_dir = storage_path / "fragments"
        self.fragments_dir.mkdir(parents=True, exist_ok=True)

    def extract_fragments(self, plans: List[ExecutionPlan]) -> List[WorkflowFragment]:
        fragments = []
        # Simple extraction: sequential step sequences of length 2 or more
        for plan in plans:
            steps = list(plan.steps.values())
            for i in range(len(steps)):
                for j in range(i + 2, len(steps) + 1):
                    sequence = steps[i:j]
                    fragment = self._create_fragment(sequence, plan.plan_id)
                    fragments.append(fragment)

        # Deduplicate and aggregate
        aggregated = self._aggregate_fragments(fragments)
        self._save_fragments(aggregated)
        return aggregated

    def _create_fragment(self, steps: List[Step], plan_id: str) -> WorkflowFragment:
        step_types = [s.step_type for s in steps]

        # Dependency shape: how steps in the sequence relate to each other
        # For simplicity, just use the relative indices of dependencies within the sequence
        id_map = {step.step_id: idx for idx, step in enumerate(steps)}
        dependency_shape = {}
        for idx, step in enumerate(steps):
            deps = [id_map[d] for d in step.dependencies if d in id_map]
            if deps:
                dependency_shape[str(idx)] = deps

        # Contracts (simplified)
        input_contract = {}
        output_contract = {}
        for step in steps:
            input_contract.update(step.inputs)
            output_contract.update(step.outputs)

        # Generate a stable fragment ID based on structural properties
        structure = {
            "step_types": step_types,
            "dependency_shape": dependency_shape
        }
        fragment_id = hashlib.sha256(json.dumps(structure, sort_keys=True).encode()).hexdigest()[:12]

        return WorkflowFragment(
            fragment_id=f"frag_{fragment_id}",
            step_types=step_types,
            dependency_shape=dependency_shape,
            input_contract=input_contract,
            output_contract=output_contract,
            source_plan_ids=[plan_id]
        )

    def _aggregate_fragments(self, fragments: List[WorkflowFragment]) -> List[WorkflowFragment]:
        by_id: Dict[str, WorkflowFragment] = {}
        for frag in fragments:
            if frag.fragment_id in by_id:
                existing = by_id[frag.fragment_id]
                if frag.source_plan_ids[0] not in existing.source_plan_ids:
                    existing.source_plan_ids.append(frag.source_plan_ids[0])
            else:
                by_id[frag.fragment_id] = frag
        return list(by_id.values())

    def _save_fragments(self, fragments: List[WorkflowFragment]):
        data = [self._fragment_to_dict(f) for f in fragments]
        with open(self.storage_path / "fragments.json", "w") as f:
            json.dump(data, f, indent=2)

    def _fragment_to_dict(self, f: WorkflowFragment) -> Dict[str, Any]:
        return {
            "fragment_id": f.fragment_id,
            "step_types": f.step_types,
            "dependency_shape": f.dependency_shape,
            "input_contract": f.input_contract,
            "output_contract": f.output_contract,
            "source_plan_ids": f.source_plan_ids
        }

    def load_fragments(self) -> List[WorkflowFragment]:
        path = self.storage_path / "fragments.json"
        if not path.exists():
            return []
        with open(path, "r") as f:
            data = json.load(f)
            return [WorkflowFragment(**d) for d in data]

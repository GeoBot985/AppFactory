from typing import List, Dict, Any, Optional
import uuid
import json
from pathlib import Path
from .models import (
    OptimizationCandidate,
    OptimizationSafetyContract,
    OptimizationBenefit,
    WorkflowFragment
)
from ..services.planner.models import ExecutionPlan, Step

class CandidateGenerator:
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.candidates_path = storage_path / "candidates.json"

    def generate_candidates(self, plan: ExecutionPlan, fragments: List[WorkflowFragment]) -> List[OptimizationCandidate]:
        candidates = []
        candidates.extend(self._find_duplicate_eliminations(plan))
        candidates.extend(self._find_io_collapses(plan))
        candidates.extend(self._find_validation_collapses(plan))
        candidates.extend(self._find_step_merges(plan))

        self._save_candidates(candidates)
        return candidates

    def _find_duplicate_eliminations(self, plan: ExecutionPlan) -> List[OptimizationCandidate]:
        candidates = []
        steps = list(plan.steps.values())
        for i, step1 in enumerate(steps):
            for j, step2 in enumerate(steps[i+1:], i+1):
                if step1.step_type == step2.step_type == "validate_output":
                    if step1.target == step2.target and step1.inputs == step2.inputs:
                        # Check if any mutation occurred between i and j on the same target
                        mutated = False
                        for k in range(i + 1, j):
                            s = steps[k]
                            if s.target == step1.target and s.step_type in ["write_file", "modify_file", "create_file"]:
                                mutated = True
                                break

                        if not mutated:
                            candidate = OptimizationCandidate(
                                candidate_id=f"cand_{uuid.uuid4().hex[:8]}",
                                source_fragment_id=None,
                                optimization_type="duplicate_elimination",
                                original_steps=[step2.step_id],
                                optimized_steps=[], # Remove step2
                                safety_contract=OptimizationSafetyContract(
                                    explicit_conditions=["No mutation on target between original validations"]
                                ),
                                expected_benefit=OptimizationBenefit(
                                    step_count_before=len(plan.steps),
                                    step_count_after=len(plan.steps) - 1,
                                    estimated_duration_before_ms=100.0, # Placeholder
                                    estimated_duration_after_ms=50.0,
                                    io_ops_before=2,
                                    io_ops_after=1
                                )
                            )
                            candidates.append(candidate)
        return candidates

    def _find_io_collapses(self, plan: ExecutionPlan) -> List[OptimizationCandidate]:
        candidates = []
        steps = list(plan.steps.values())
        for i in range(len(steps) - 1):
            s1 = steps[i]
            s2 = steps[i+1]
            if s1.step_type == "write_file" and s2.step_type == "read_file" and s1.target == s2.target:
                candidate = OptimizationCandidate(
                    candidate_id=f"cand_{uuid.uuid4().hex[:8]}",
                    source_fragment_id=None,
                    optimization_type="io_collapse",
                    original_steps=[s2.step_id],
                    optimized_steps=[], # S2 can be collapsed if we keep S1's content in memory
                    safety_contract=OptimizationSafetyContract(
                        explicit_conditions=["Target written and then read immediately"]
                    ),
                    expected_benefit=OptimizationBenefit(
                        step_count_before=len(plan.steps),
                        step_count_after=len(plan.steps) - 1,
                        estimated_duration_before_ms=200.0,
                        estimated_duration_after_ms=100.0,
                        io_ops_before=2,
                        io_ops_after=1
                    )
                )
                candidates.append(candidate)
        return candidates

    def _find_validation_collapses(self, plan: ExecutionPlan) -> List[OptimizationCandidate]:
        candidates = []
        steps = list(plan.steps.values())
        for i in range(len(steps) - 1):
            s1 = steps[i]
            s2 = steps[i+1]
            if s1.step_type == "verify_file_exists" and s2.step_type == "validate_output" and s1.target == s2.target:
                # validate_output implies verify_file_exists
                candidate = OptimizationCandidate(
                    candidate_id=f"cand_{uuid.uuid4().hex[:8]}",
                    source_fragment_id=None,
                    optimization_type="validation_collapse",
                    original_steps=[s1.step_id],
                    optimized_steps=[], # Remove weaker validation
                    safety_contract=OptimizationSafetyContract(
                        explicit_conditions=["Stronger validation follows weaker one"]
                    ),
                    expected_benefit=OptimizationBenefit(
                        step_count_before=len(plan.steps),
                        step_count_after=len(plan.steps) - 1,
                        estimated_duration_before_ms=50.0,
                        estimated_duration_after_ms=25.0,
                        io_ops_before=2,
                        io_ops_after=1
                    )
                )
                candidates.append(candidate)
        return candidates

    def _find_step_merges(self, plan: ExecutionPlan) -> List[OptimizationCandidate]:
        # Placeholder for complex merges
        return []

    def _save_candidates(self, candidates: List[OptimizationCandidate]):
        if not self.candidates_path.exists():
            existing_data = []
        else:
            with open(self.candidates_path, "r") as f:
                existing_data = json.load(f)

        # Deduplication based on optimization_type and original_steps
        existing_signatures = {
            (d["optimization_type"], tuple(sorted(d["original_steps"])))
            for d in existing_data
        }

        for cand in candidates:
            signature = (cand.optimization_type, tuple(sorted(cand.original_steps)))
            if signature not in existing_signatures:
                existing_data.append(self._candidate_to_dict(cand))
                existing_signatures.add(signature)

        with open(self.candidates_path, "w") as f:
            json.dump(existing_data, f, indent=2)

    def _candidate_to_dict(self, c: OptimizationCandidate) -> Dict[str, Any]:
        return {
            "candidate_id": c.candidate_id,
            "source_fragment_id": c.source_fragment_id,
            "optimization_type": c.optimization_type,
            "original_steps": c.original_steps,
            "optimized_steps": c.optimized_steps,
            "safety_contract": vars(c.safety_contract),
            "expected_benefit": vars(c.expected_benefit),
            "status": c.status
        }

    def load_candidates(self, status: Optional[str] = None) -> List[OptimizationCandidate]:
        if not self.candidates_path.exists():
            return []
        with open(self.candidates_path, "r") as f:
            data = json.load(f)
            candidates = []
            for d in data:
                d["safety_contract"] = OptimizationSafetyContract(**d["safety_contract"])
                d["expected_benefit"] = OptimizationBenefit(**d["expected_benefit"])
                candidates.append(OptimizationCandidate(**d))

            if status:
                candidates = [c for c in candidates if c.status == status]
            return candidates

    def update_candidate_status(self, candidate_id: str, status: str):
        if not self.candidates_path.exists():
            return
        with open(self.candidates_path, "r") as f:
            data = json.load(f)

        for d in data:
            if d["candidate_id"] == candidate_id:
                d["status"] = status
                break

        with open(self.candidates_path, "w") as f:
            json.dump(data, f, indent=2)

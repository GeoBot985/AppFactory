from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime

@dataclass
class WorkflowFragment:
    fragment_id: str
    step_types: List[str]
    dependency_shape: Dict[str, Any]
    input_contract: Dict[str, Any]
    output_contract: Dict[str, Any]
    source_plan_ids: List[str] = field(default_factory=list)

@dataclass
class OptimizationSafetyContract:
    preserves_step_order_semantics: bool = True
    preserves_outputs: bool = True
    preserves_retry_boundaries: bool = True
    preserves_rollback_behavior: bool = True
    preserves_verification_comparability: bool = True
    explicit_conditions: List[str] = field(default_factory=list)

@dataclass
class OptimizationBenefit:
    step_count_before: int
    step_count_after: int
    estimated_duration_before_ms: float
    estimated_duration_after_ms: float
    io_ops_before: int
    io_ops_after: int
    observed_duration_before_ms: Optional[float] = None
    observed_duration_after_ms: Optional[float] = None

@dataclass
class OptimizationCandidate:
    candidate_id: str
    source_fragment_id: Optional[str]
    optimization_type: Literal[
        "step_merge",
        "duplicate_elimination",
        "validation_collapse",
        "io_collapse",
        "fragment_reuse"
    ]
    original_steps: List[str] # List of step IDs
    optimized_steps: List[Dict[str, Any]] # Serialized step definitions for the new steps
    safety_contract: OptimizationSafetyContract
    expected_benefit: OptimizationBenefit
    status: Literal["proposed", "verified", "rejected", "adopted"] = "proposed"

@dataclass
class OptimizedPlanVariant:
    variant_id: str
    source_plan_id: str
    optimization_candidate_ids: List[str]
    execution_plan: Dict[str, Any] # Serialized ExecutionPlan
    verification_status: Literal["pending", "passed", "failed"] = "pending"

@dataclass
class OptimizationProvenance:
    candidate_id: str
    source_plan_id: str
    source_run_ids: List[str] = field(default_factory=list)
    derived_fragment_ids: List[str] = field(default_factory=list)
    verification_result_ids: List[str] = field(default_factory=list)
    adopted_at: Optional[datetime] = None

@dataclass
class OptimizationRecord:
    adopted_optimizations: List[Dict[str, Any]] = field(default_factory=list)

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime

@dataclass
class MacroInputContract:
    required_inputs: List[str]
    optional_inputs: List[str] = field(default_factory=list)
    type_constraints: Dict[str, str] = field(default_factory=dict)
    default_bindings: Dict[str, str] = field(default_factory=dict)

@dataclass
class MacroOutputContract:
    produced_outputs: List[str]
    output_types: Dict[str, str] = field(default_factory=dict)
    postconditions: List[str] = field(default_factory=list)

@dataclass
class MacroSafetyContract:
    workspace_bound: bool = True
    preserves_retry_boundaries: bool = True
    preserves_rollback_behavior: bool = True
    requires_verification_before_use: bool = True
    max_expansion_depth: int = 1

@dataclass
class MacroRollbackContract:
    reversible: bool = True
    rollback_steps_preserved: bool = True
    compensation_requirements: List[str] = field(default_factory=list)

@dataclass
class WorkflowMacro:
    macro_id: str
    name: str
    version: str
    source_fragment_id: str
    description: str
    step_template: List[Dict[str, Any]] # List of step definitions with parameters
    input_contract: MacroInputContract
    output_contract: MacroOutputContract
    dependency_shape: Dict[str, Any]
    safety_contract: MacroSafetyContract
    rollback_contract: MacroRollbackContract
    verification_status: Literal[
        "pending",
        "verified",
        "rejected",
        "deprecated"
    ] = "pending"

@dataclass
class MacroLibrary:
    library_id: str
    macros: List[WorkflowMacro] = field(default_factory=list)
    active_versions: Dict[str, str] = field(default_factory=dict)  # macro name -> version

@dataclass
class MacroPromotionCandidate:
    candidate_id: str
    source_fragment_id: str
    source_variant_id: Optional[str] = None
    proposed_name: str = ""
    proposed_version: str = "v1"
    contracts: Dict[str, Any] = field(default_factory=dict)
    status: Literal[
        "proposed",
        "verified",
        "adopted",
        "rejected"
    ] = "proposed"

@dataclass
class MacroExpansionResult:
    expansion_id: str
    macro_id: str
    bound_inputs: Dict[str, Any]
    expanded_steps: List[Dict[str, Any]]
    status: Literal[
        "expanded",
        "failed"
    ] = "expanded"
    issues: List[str] = field(default_factory=list)

@dataclass
class MacroProvenance:
    macro_id: str
    source_fragment_id: str
    source_plan_ids: List[str] = field(default_factory=list)
    source_run_ids: List[str] = field(default_factory=list)
    source_variant_ids: List[str] = field(default_factory=list)
    verification_result_ids: List[str] = field(default_factory=list)
    adopted_at: Optional[datetime] = None

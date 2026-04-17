from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional, Dict, Any, List

@dataclass
class SingleCommandRequest:
    request_id: str
    input_text: str
    target_environment: Literal["dev", "staging", "prod"]
    strictness: Literal["strict", "tolerant", "debug"]
    workspace_mode: Literal["in_place", "cloned_workspace", "temp_workspace"]
    allow_repair: bool = True
    max_repair_iterations: int = 3

@dataclass
class SingleCommandResult:
    request_id: str
    compile_status: str
    repair_iterations: int
    plan_id: Optional[str] = None
    routing_decision_id: Optional[str] = None
    run_id: Optional[str] = None
    verification_result_id: Optional[str] = None
    promotion_decision_id: Optional[str] = None
    final_status: Literal[
        "completed",
        "completed_with_warnings",
        "blocked",
        "failed",
        "rejected"
    ] = "failed"
    consistency_outcome: Optional[str] = None
    summary: Dict[str, Any] = field(default_factory=dict)

# Failure Codes
SC_COMPILE_BLOCKED = "SC_COMPILE_BLOCKED"
SC_PLAN_INVALID = "SC_PLAN_INVALID"
SC_EXECUTION_FAILED = "SC_EXECUTION_FAILED"
SC_VERIFICATION_FAILED = "SC_VERIFICATION_FAILED"
SC_PROMOTION_REJECTED = "SC_PROMOTION_REJECTED"
SC_REPAIR_EXHAUSTED = "SC_REPAIR_EXHAUSTED"

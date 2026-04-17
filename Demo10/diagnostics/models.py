from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional, List
from pydantic import BaseModel, Field
import uuid

RootCauseCategory = Literal[
    "input_error",
    "plan_error",
    "execution_error",
    "environment_error",
    "transient_error",
    "rollback_error",
    "verification_error",
    "policy_error"
]

class FailureSignature(BaseModel):
    signature_id: str
    error_code: str
    step_type: str
    operation_type: Optional[str] = None
    target: Optional[str] = None
    context_hash: str

class RootCause(BaseModel):
    root_cause_id: str
    category: RootCauseCategory
    subcategory: str
    description: str
    deterministic: bool = True

class FailureInstance(BaseModel):
    failure_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    step_id: Optional[str] = None
    error_code: str
    signature_id: str
    root_cause_id: str
    timestamp: datetime = Field(default_factory=datetime.now)

class FailurePattern(BaseModel):
    pattern_id: str
    signature_id: str
    error_code: str
    root_cause_id: str
    occurrences: int = 0
    first_seen: datetime
    last_seen: datetime
    impact_score: float = 0.0
    affected_runs: List[str] = Field(default_factory=list)

class RootCauseSummary(BaseModel):
    root_cause: str
    count: int
    affected_runs: List[str]

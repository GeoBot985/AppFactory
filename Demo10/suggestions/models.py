from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional, List, Union
from pydantic import BaseModel, Field
import uuid

SuggestionCategory = Literal[
    "input_fix",
    "plan_fix",
    "execution_fix",
    "environment_fix",
    "retry_tuning",
    "rollback_fix",
    "verification_fix",
    "policy_fix"
]

SuggestedActionType = Literal[
    "set_field",
    "add_missing_value",
    "select_candidate",
    "adjust_parameter",
    "rerun_with_context",
    "inspect_artifact",
    "verify_path",
    "install_dependency"
]

class SuggestedAction(BaseModel):
    action_type: SuggestedActionType
    target_field: Optional[str] = None
    value: Optional[str] = None
    instructions: str

class RepairSuggestion(BaseModel):
    suggestion_id: str = Field(default_factory=lambda: f"sug_{uuid.uuid4().hex[:8]}")
    root_cause_id: str
    category: SuggestionCategory
    description: str
    actions: List[SuggestedAction]
    confidence: Literal["high", "medium", "low"]
    deterministic: bool = True

class SuggestionMapping(BaseModel):
    root_cause_id: str
    suggestion_templates: List[RepairSuggestion]

class SuggestionUsage(BaseModel):
    suggestion_id: str
    run_id: str
    applied: bool
    resolved_issue: bool
    timestamp: datetime = Field(default_factory=datetime.now)

class SuggestionEffectiveness(BaseModel):
    suggestion_id: str
    usage_count: int = 0
    application_count: int = 0
    resolution_count: int = 0
    avg_steps_to_resolution: float = 0.0

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

class ReRunType(Enum):
    RERUN_FAILED_TASK = "rerun_failed_task"
    RERUN_FROM_TASK = "rerun_from_task"
    RERUN_VALIDATION_SUFFIX = "rerun_validation_suffix"

@dataclass
class ReRunRequest:
    base_run_id: str
    rerun_type: ReRunType
    start_task_id: Optional[str] = None
    reason: str = ""
    rerun_depth: int = 0
    task_id: Optional[str] = None # Added for Policy Engine compatibility

@dataclass
class ReRunPlan:
    base_run_id: str
    rerun_id: str
    start_task_id: str
    end_task_id: Optional[str] = None
    reused_tasks: List[str] = field(default_factory=list)
    rerun_tasks: List[str] = field(default_factory=list)
    invalidated_tasks: List[str] = field(default_factory=list)
    artifact_reuse_summary: Dict[str, List[str]] = field(default_factory=dict)
    reason: str = ""

@dataclass
class ReRunLineage:
    base_run_id: str
    rerun_id: str
    rerun_reason: str
    requested_start_task_id: Optional[str]
    resolved_rerun_range: List[str]
    artifact_reuse_summary: Dict[str, Any]
    invalidated_task_ids: List[str]

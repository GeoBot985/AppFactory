from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime

class CompiledRunStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    STOPPED = "stopped"

class CompiledTaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    INVALIDATED = "invalidated"
    REUSED = "reused"
    RERUN_PENDING = "rerun_pending"
    RERUN_SUCCEEDED = "rerun_succeeded"
    RERUN_FAILED = "rerun_failed"

@dataclass
class CompiledTaskState:
    task_id: str
    task_type: str
    status: CompiledTaskStatus = CompiledTaskStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    attempt_count: int = 0
    result_summary: str = ""
    failure_class: Optional[str] = None
    artifacts: Dict[str, Any] = field(default_factory=dict)
    bundle: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "depends_on": self.depends_on,
            "attempt_count": self.attempt_count,
            "result_summary": self.result_summary,
            "failure_class": self.failure_class,
            "artifacts": self.artifacts,
            "bundle": self.bundle
        }

@dataclass
class CompiledPlanRun:
    compiled_plan_id: str
    run_id: str
    overall_status: CompiledRunStatus = CompiledRunStatus.PENDING
    tasks_total: int = 0
    tasks_succeeded: int = 0
    tasks_failed: int = 0
    tasks_skipped: int = 0
    current_task_id: Optional[str] = None
    task_states: Dict[str, CompiledTaskState] = field(default_factory=dict)
    started_at: Optional[str] = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    fail_fast: bool = True
    base_run_id: Optional[str] = None
    rerun_lineage: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "compiled_plan_id": self.compiled_plan_id,
            "run_id": self.run_id,
            "overall_status": self.overall_status.value,
            "tasks_total": self.tasks_total,
            "tasks_succeeded": self.tasks_succeeded,
            "tasks_failed": self.tasks_failed,
            "tasks_skipped": self.tasks_skipped,
            "current_task_id": self.current_task_id,
            "task_states": {tid: ts.to_dict() for tid, ts in self.task_states.items()},
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "fail_fast": self.fail_fast,
            "base_run_id": self.base_run_id,
            "rerun_lineage": self.rerun_lineage
        }

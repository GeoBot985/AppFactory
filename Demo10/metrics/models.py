from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime

@dataclass
class StageMetrics:
    stage_name: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata
        }

@dataclass
class ModelUsage:
    model_name: str
    call_count: int = 0
    total_tokens: Optional[int] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_latency_ms: float = 0.0
    success_count: int = 0
    failure_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "call_count": self.call_count,
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_latency_ms": self.total_latency_ms,
            "success_count": self.success_count,
            "failure_count": self.failure_count
        }

@dataclass
class TaskMetrics:
    task_id: str
    task_type: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    attempts: int = 0
    repair_cycles: int = 0
    syntax_failures: int = 0
    coherence_failures: int = 0
    test_failures: int = 0
    failure_class: Optional[str] = None

    model_usage: Dict[str, ModelUsage] = field(default_factory=dict)
    stages: Dict[str, StageMetrics] = field(default_factory=dict)

    context_files_count: int = 0
    context_size_chars: int = 0

    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    diff_size_bytes: int = 0

    slow_step: bool = False
    slow_reason: Optional[str] = None
    anomaly_flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "attempts": self.attempts,
            "repair_cycles": self.repair_cycles,
            "syntax_failures": self.syntax_failures,
            "coherence_failures": self.coherence_failures,
            "test_failures": self.test_failures,
            "failure_class": self.failure_class,
            "model_usage": {k: v.to_dict() for k, v in self.model_usage.items()},
            "stages": {k: v.to_dict() for k, v in self.stages.items()},
            "context_files_count": self.context_files_count,
            "context_size_chars": self.context_size_chars,
            "files_changed": self.files_changed,
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "diff_size_bytes": self.diff_size_bytes,
            "slow_step": self.slow_step,
            "slow_reason": self.slow_reason,
            "anomaly_flags": self.anomaly_flags
        }

@dataclass
class RunMetrics:
    run_id: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    total_duration_ms: float = 0.0

    tasks: Dict[str, TaskMetrics] = field(default_factory=dict)
    high_level_stages: Dict[str, StageMetrics] = field(default_factory=dict)

    # Aggregates
    total_attempts: int = 0
    total_model_calls: int = 0
    avg_generation_latency_ms: float = 0.0
    total_files_changed: int = 0
    total_lines_added: int = 0
    total_lines_removed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_duration_ms": self.total_duration_ms,
            "tasks": {k: v.to_dict() for k, v in self.tasks.items()},
            "high_level_stages": {k: v.to_dict() for k, v in self.high_level_stages.items()},
            "total_attempts": self.total_attempts,
            "total_model_calls": self.total_model_calls,
            "avg_generation_latency_ms": self.avg_generation_latency_ms,
            "total_files_changed": self.total_files_changed,
            "total_lines_added": self.total_lines_added,
            "total_lines_removed": self.total_lines_removed
        }

@dataclass
class RunSummary:
    run_id: str
    total_duration_ms: float
    tasks_executed: int
    tasks_failed: int
    retry_count: int
    model_calls: int
    avg_generation_latency_ms: float
    tests_run: int
    tests_passed: int
    tests_failed: int
    files_changed: int
    risk_level: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "total_duration_ms": self.total_duration_ms,
            "tasks_executed": self.tasks_executed,
            "tasks_failed": self.tasks_failed,
            "retry_count": self.retry_count,
            "model_calls": self.model_calls,
            "avg_generation_latency_ms": self.avg_generation_latency_ms,
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "files_changed": self.files_changed,
            "risk_level": self.risk_level
        }

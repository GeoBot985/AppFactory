from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AttemptConfig:
    max_total_attempts: int = 3
    allow_full_regenerate_after_patch_failure: bool = True
    allow_repair_after_validation_failure: bool = True


@dataclass
class AttemptRecord:
    attempt_index: int
    attempt_type: str
    input_summary: str
    operation_plan_summary: str
    validation_result_summary: str
    failure_class: str = ""
    repair_strategy_used: str = ""
    success: bool = False
    stop_reason: str = ""
    targeted_files: list[str] = field(default_factory=list)
    diff_preview_summary: str = ""
    error_summary: str = ""
    disk_write_performed: bool = False
    failure_fingerprint: str = ""
    context_summary: str = ""


@dataclass
class AttemptLedger:
    attempts: list[AttemptRecord] = field(default_factory=list)
    final_outcome: str = ""
    applied_attempt_index: int = 0
    stopped_reason: str = ""

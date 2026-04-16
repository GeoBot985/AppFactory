from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScopeConfig:
    max_primary_edit_files: int = 2
    max_secondary_edit_files: int = 2
    max_total_editable_files: int = 3
    max_target_symbols: int = 3


@dataclass
class TargetSymbol:
    symbol_name: str
    resolution_status: str
    file_candidates: list[str] = field(default_factory=list)
    region_hint: str = ""


@dataclass
class ScopeContract:
    task_id: str
    primary_target_files: list[str] = field(default_factory=list)
    secondary_edit_files: list[str] = field(default_factory=list)
    secondary_context_files: list[str] = field(default_factory=list)
    read_only_context_files: list[str] = field(default_factory=list)
    excluded_files: list[str] = field(default_factory=list)
    target_symbols: list[TargetSymbol] = field(default_factory=list)
    target_regions: dict[str, list[str]] = field(default_factory=dict)
    targeting_reasons: dict[str, str] = field(default_factory=dict)
    scope_confidence: str = "low"
    scope_class: str = "repo_broad"
    scope_policy_result: str = "scope_blocked_low_confidence"
    warnings: list[str] = field(default_factory=list)
    expansion_log: list[dict] = field(default_factory=list)

    @property
    def editable_files(self) -> list[str]:
        return self.primary_target_files + self.secondary_edit_files

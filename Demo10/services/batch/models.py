from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PythonModuleView:
    relative_path: str
    module_path: str
    imports: list[str] = field(default_factory=list)
    from_imports: dict[str, list[str]] = field(default_factory=dict)
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    duplicate_symbols: list[str] = field(default_factory=list)
    parse_status: str = "metadata_only"


@dataclass
class BatchFileSummary:
    path: str
    operation_type: str
    purpose: str
    symbols_added: list[str] = field(default_factory=list)
    symbols_removed: list[str] = field(default_factory=list)
    imports_added: list[str] = field(default_factory=list)
    imports_removed: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class BatchFinding:
    status: str
    message: str
    impacted_files: list[str] = field(default_factory=list)


@dataclass
class BatchValidationSummary:
    batch_id: str
    spec_item_id: str
    target_files: list[str] = field(default_factory=list)
    file_summaries: list[BatchFileSummary] = field(default_factory=list)
    planned_symbols_added: list[str] = field(default_factory=list)
    planned_symbols_modified: list[str] = field(default_factory=list)
    planned_symbols_removed: list[str] = field(default_factory=list)
    import_changes: list[str] = field(default_factory=list)
    entrypoint_changes: list[str] = field(default_factory=list)
    batch_validation_status: str = "batch_valid"
    batch_failure_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    impacted_files: list[str] = field(default_factory=list)
    complexity: str = "single_file_simple"

from __future__ import annotations

from pathlib import Path

from services.batch.models import BatchFileSummary, BatchValidationSummary
from services.batch.python_symbols import extract_python_module_view
from services.batch.simulated_workspace import build_simulated_workspace_overlay


MAX_AFFECTED_FILES = 5
MAX_NEW_FILES = 3


def validate_batch_coherence(project_root: str | Path, operations, simulated_files: dict[str, str | None]) -> BatchValidationSummary:
    target_files = [op.path for op in operations]
    summary = BatchValidationSummary(
        batch_id="batch_1",
        spec_item_id=operations[0].op_id if operations else "",
        target_files=target_files,
    )
    if len(target_files) > MAX_AFFECTED_FILES:
        summary.batch_validation_status = "batch_invalid_unknown"
        summary.batch_failure_reasons.append(f"policy_blocked_complex_batch: affected_files={len(target_files)}")
        summary.impacted_files = target_files
        summary.complexity = "multi_file_complex"
        return summary

    root = Path(project_root).expanduser().resolve()
    before_views = {}
    after_views = {}
    existed_before: dict[str, bool] = {}
    new_files = 0
    changed_modules = set()

    for op in operations:
        rel = op.path
        abs_path = root / rel
        existed_before[rel] = abs_path.exists()
        before_text = ""
        if abs_path.exists() and abs_path.is_file():
            try:
                before_text = abs_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                before_text = ""
        after_text = simulated_files.get(rel)
        purpose = op.reason or op.source_stage or op.op_type
        file_summary = BatchFileSummary(path=rel, operation_type=op.op_type, purpose=purpose)
        if rel.endswith(".py"):
            before_view = extract_python_module_view(rel, before_text) if before_text else extract_python_module_view(rel, "")
            after_view = extract_python_module_view(rel, after_text or "") if after_text is not None else None
            before_views[rel] = before_view
            after_views[rel] = after_view
            before_symbols = set(before_view.functions + before_view.classes)
            after_symbols = set(after_view.functions + after_view.classes) if after_view else set()
            file_summary.symbols_added = sorted(after_symbols - before_symbols)
            file_summary.symbols_removed = sorted(before_symbols - after_symbols)
            before_imports = set(before_view.imports + [f"{module}:{name}" for module, names in before_view.from_imports.items() for name in names])
            after_imports = set(after_view.imports + [f"{module}:{name}" for module, names in after_view.from_imports.items() for name in names]) if after_view else set()
            file_summary.imports_added = sorted(after_imports - before_imports)
            file_summary.imports_removed = sorted(before_imports - after_imports)
            file_summary.depends_on = sorted(set(list((after_view.from_imports or {}).keys()) + list(after_view.imports))) if after_view else []
            summary.planned_symbols_added.extend(f"{rel}:{name}" for name in file_summary.symbols_added)
            summary.planned_symbols_removed.extend(f"{rel}:{name}" for name in file_summary.symbols_removed)
            if file_summary.symbols_added or file_summary.symbols_removed:
                summary.planned_symbols_modified.append(rel)
            summary.import_changes.extend(f"{rel}:{item}" for item in file_summary.imports_added + file_summary.imports_removed)
            if after_view and after_view.module_path:
                changed_modules.add(after_view.module_path)
            if op.op_type == "create_file":
                new_files += 1
                if rel.endswith(("main.py", "app.py", "server.py", "cli.py")):
                    summary.entrypoint_changes.append(rel)
            summary.file_summaries.append(file_summary)

    if new_files > MAX_NEW_FILES:
        summary.batch_validation_status = "batch_invalid_unknown"
        summary.batch_failure_reasons.append(f"policy_blocked_complex_batch: new_files={new_files}")
        summary.impacted_files = target_files
        summary.complexity = "multi_file_complex"
        return summary

    module_to_symbols = {}
    path_to_module = {}
    for rel, view in after_views.items():
        if not view:
            continue
        path_to_module[rel] = view.module_path
        module_to_symbols[view.module_path] = set(view.functions + view.classes)
        if view.duplicate_symbols:
            summary.batch_validation_status = "batch_invalid_duplicate_symbol"
            summary.batch_failure_reasons.append(f"{rel}: duplicate symbols {', '.join(view.duplicate_symbols)}")
            summary.impacted_files.append(rel)

    for rel, view in after_views.items():
        if not view or view.parse_status == "parse_error":
            summary.batch_validation_status = "batch_invalid_unparseable_after_change"
            summary.batch_failure_reasons.append(f"{rel}: unparseable after change")
            summary.impacted_files.append(rel)
            continue
        for module_name, names in view.from_imports.items():
            normalized = module_name.lstrip(".")
            if normalized in module_to_symbols:
                available = module_to_symbols[normalized]
                missing = [name for name in names if name not in available and name != "*"]
                if missing:
                    removed_referenced = False
                    for other_rel, other_view in before_views.items():
                        if other_view and other_view.module_path == normalized:
                            removed = set(other_view.functions + other_view.classes) - available
                            if any(name in removed for name in missing):
                                summary.batch_validation_status = "batch_invalid_removed_symbol_still_referenced"
                                removed_referenced = True
                                break
                    if not removed_referenced:
                        summary.batch_validation_status = "batch_invalid_broken_import"
                    summary.batch_failure_reasons.append(f"{rel}: missing import target {normalized} -> {', '.join(missing)}")
                    summary.impacted_files.extend([rel] + [path for path, mod in path_to_module.items() if mod == normalized])

    imported_modules = set()
    for view in after_views.values():
        if not view:
            continue
        imported_modules.update(module.lstrip(".") for module in view.imports)
        imported_modules.update(module.lstrip(".") for module in view.from_imports)
    for rel, view in after_views.items():
        if not view:
            continue
        if not existed_before.get(rel, False) and view.module_path not in imported_modules and not rel.endswith(("main.py", "app.py", "server.py", "cli.py")):
            summary.warnings.append(f"{rel}: orphan new file not referenced in affected batch")

    impacted = sorted(set(item for item in summary.impacted_files if item))
    summary.impacted_files = impacted
    if summary.batch_validation_status.startswith("batch_invalid"):
        pass
    elif summary.warnings:
        summary.batch_validation_status = "batch_valid_with_warnings"
    else:
        summary.batch_validation_status = "batch_valid"

    changed_count = len(target_files)
    if changed_count == 1:
        summary.complexity = "single_file_simple"
    elif changed_count <= 3 and len(summary.import_changes) <= 4:
        summary.complexity = "multi_file_related"
    else:
        summary.complexity = "multi_file_complex"
    return summary

from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path

from services.attempts.models import AttemptRecord
from services.context.file_inventory import InventoryFile, WorkspaceInventoryBuilder
from services.context.file_selector import normalize_terms
from services.targeting.models import ScopeConfig, ScopeContract, TargetSymbol


PROTECTED_PATTERNS = (".venv/", "venv/", "__pycache__/", ".git/", "node_modules/", "dist/", "build/")


class ScopeBuilder:
    def __init__(self, config: ScopeConfig | None = None):
        self.config = config or ScopeConfig()
        self.inventory_builder = WorkspaceInventoryBuilder()
        self._inventory_cache: dict[str, list[InventoryFile]] = {}

    def build(self, project_root: str, task_id: str, spec_text: str, task_target: str = "", prior_history: list[AttemptRecord] | None = None, session_context: dict | None = None) -> ScopeContract:
        prior_history = prior_history or []
        inventory = self._inventory_cache.get(project_root)
        if inventory is None:
            inventory = self.inventory_builder.build(project_root)
            self._inventory_cache[project_root] = inventory

        contract = ScopeContract(task_id=task_id)
        contract.excluded_files = self._collect_protected_paths(project_root)
        terms = normalize_terms(spec_text)
        explicit_paths = {term for term in terms if "/" in term or term.endswith(".py") or term.endswith(".json") or term.endswith(".yaml") or term.endswith(".yml")}
        symbol_terms = [term for term in terms if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", term)]
        failure_files = [path for attempt in prior_history for path in attempt.targeted_files if attempt.failure_class]
        if session_context:
            failure_files.extend(session_context.get("failure_files", []))
            failure_files = list(set(failure_files))

        session_primary = session_context.get("primary_files", []) if session_context else []

        scored: list[tuple[int, str, InventoryFile]] = []
        symbol_match_paths: set[str] = set()
        for item in inventory:
            path = item.relative_path
            if any(pattern in f"{path}/" for pattern in PROTECTED_PATTERNS):
                continue
            score = 0
            reason = ""
            if task_target and path == task_target:
                score += 120
                reason = "explicit_task_target"
            elif any(explicit == path or explicit.endswith(path.split("/")[-1]) for explicit in explicit_paths):
                score += 110
                reason = "explicit_path_match"
            elif path in failure_files:
                score += 95
                reason = "previous_attempt_failure_file"
            elif path in session_primary:
                score += 30
                reason = "session_working_set_boost"
            else:
                filename = path.split("/")[-1].lower()
                if any(term in filename for term in terms):
                    score += 60
                    reason = "filename_keyword_match"
                elif any(term in path.lower() for term in terms):
                    score += 40
                    reason = "directory_keyword_match"
                elif item.is_entrypoint:
                    score += 20
                    reason = "entrypoint_candidate"
                elif item.is_config:
                    score += 14
                    reason = "config_candidate"
            if item.language == "python":
                structure = item.structure or {}
                names = set(structure.get("functions", []) + structure.get("classes", []))
                exact_symbols = sorted(term for term in symbol_terms if term in names)
                if exact_symbols:
                    score += 100
                    reason = "explicit_symbol_match"
                    symbol_match_paths.add(path)
                    for symbol in exact_symbols:
                        contract.target_symbols.append(
                            TargetSymbol(
                                symbol_name=symbol,
                                resolution_status="symbol_resolved_exact",
                                file_candidates=[path],
                                region_hint=f"symbol:{symbol}",
                            )
                        )
                        contract.target_regions.setdefault(path, []).append(f"symbol:{symbol}")
            if score > 0:
                scored.append((score, reason, item))

        dedup_symbols: dict[tuple[str, tuple[str, ...]], TargetSymbol] = {}
        for symbol in contract.target_symbols:
            dedup_symbols[(symbol.symbol_name, tuple(symbol.file_candidates))] = symbol
        contract.target_symbols = list(dedup_symbols.values())[: self.config.max_target_symbols]

        scored.sort(key=lambda row: (-row[0], row[2].relative_path))
        task_target_explicit = False
        if task_target:
            target_path = Path(project_root) / task_target
            task_target_explicit = target_path.exists() or task_target.lower() in spec_text.lower()
        if task_target and task_target_explicit:
            contract.primary_target_files = [task_target]
            contract.targeting_reasons[task_target] = "explicit_task_target"
        elif scored:
            contract.primary_target_files = [scored[0][2].relative_path]
            contract.targeting_reasons[scored[0][2].relative_path] = scored[0][1]
        if symbol_match_paths and not task_target:
            contract.primary_target_files = [sorted(symbol_match_paths)[0]]
            contract.targeting_reasons[contract.primary_target_files[0]] = "explicit_symbol_match"

        editable_set = set(contract.primary_target_files)
        for _, reason, item in scored:
            if item.relative_path in editable_set:
                continue
            if item.relative_path in symbol_match_paths:
                contract.read_only_context_files.append(item.relative_path)
                contract.targeting_reasons[item.relative_path] = "symbol_related_context"
                continue
            if len(contract.secondary_edit_files) < self.config.max_secondary_edit_files and item.relative_path in failure_files:
                contract.secondary_edit_files.append(item.relative_path)
                contract.targeting_reasons[item.relative_path] = "previous_attempt_failure_file; scope_expansion_candidate"
                editable_set.add(item.relative_path)
            elif len(contract.read_only_context_files) < 4:
                contract.read_only_context_files.append(item.relative_path)
                contract.targeting_reasons[item.relative_path] = reason
        else:
            pass

        if not contract.primary_target_files:
            anchors = [item for item in inventory if item.is_entrypoint or item.is_config][:2]
            contract.read_only_context_files = [item.relative_path for item in anchors]
            for item in anchors:
                contract.targeting_reasons[item.relative_path] = "weak_match_fallback"
            contract.warnings.append("no clear editable target found")
        if any(term in spec_text.lower() for term in ["everything", "everywhere", "whole repo", "entire repo", "all modules", "refactor everything"]):
            contract.warnings.append("task text implies repo-broad scope")

        contract.scope_confidence = self._scope_confidence(contract)
        contract.scope_class = self._scope_class(contract)
        contract.scope_policy_result = self._policy_result(contract)
        if not contract.target_symbols and symbol_terms:
            unresolved = [term for term in symbol_terms if len(term) > 2][: self.config.max_target_symbols]
            for symbol in unresolved:
                contract.target_symbols.append(TargetSymbol(symbol_name=symbol, resolution_status="symbol_unresolved", file_candidates=[]))
            if unresolved:
                contract.warnings.append(f"unresolved symbols: {', '.join(unresolved)}")
        return contract

    def allow_scope_expansion(self, contract: ScopeContract, candidate_file: str, reason: str, attempt_index: int) -> ScopeContract:
        if candidate_file in contract.editable_files or candidate_file in contract.excluded_files:
            return contract
        if len(contract.editable_files) >= self.config.max_total_editable_files:
            contract.warnings.append(f"scope expansion denied for {candidate_file}: max editable files reached")
            contract.scope_policy_result = "scope_blocked_too_broad"
            return contract
        contract.secondary_edit_files.append(candidate_file)
        contract.targeting_reasons[candidate_file] = reason
        contract.expansion_log.append({"file": candidate_file, "reason": reason, "attempt_index": attempt_index})
        contract.scope_class = self._scope_class(contract)
        contract.scope_policy_result = self._policy_result(contract)
        return contract

    def to_dict(self, contract: ScopeContract) -> dict:
        return asdict(contract)

    def _scope_confidence(self, contract: ScopeContract) -> str:
        if contract.primary_target_files and any(reason in {"explicit_task_target", "explicit_path_match", "explicit_symbol_match"} for reason in contract.targeting_reasons.values()):
            return "high"
        if contract.primary_target_files:
            return "medium"
        return "low"

    def _scope_class(self, contract: ScopeContract) -> str:
        total_editable = len(contract.editable_files)
        if total_editable == 0:
            return "repo_broad"
        if total_editable == 1 and len(contract.target_symbols) == 1:
            return "single_symbol_local"
        if total_editable == 1:
            return "single_file_local"
        if total_editable <= 3:
            return "multi_file_related"
        return "cross_module_expansion"

    def _policy_result(self, contract: ScopeContract) -> str:
        if contract.scope_confidence == "low" and not contract.primary_target_files:
            if any("repo-broad" in warning or "implies repo-broad" in warning for warning in contract.warnings):
                return "scope_blocked_low_confidence"
            return "scope_allowed_with_warning"
        if any("repo-broad" in warning or "implies repo-broad" in warning for warning in contract.warnings):
            return "scope_blocked_too_broad"
        if len(contract.editable_files) > self.config.max_total_editable_files:
            return "scope_blocked_too_broad"
        if contract.scope_class in {"cross_module_expansion", "repo_broad"} and contract.scope_confidence == "low":
            return "scope_blocked_too_broad"
        if contract.scope_confidence == "medium" and len(contract.editable_files) > 1:
            return "scope_allowed_with_warning"
        return "scope_allowed"

    def _collect_protected_paths(self, project_root: str) -> list[str]:
        root = Path(project_root)
        protected: list[str] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if any(pattern in f"{rel}/" or rel.startswith(pattern.rstrip("/")) for pattern in PROTECTED_PATTERNS):
                protected.append(rel)
        return sorted(set(protected))

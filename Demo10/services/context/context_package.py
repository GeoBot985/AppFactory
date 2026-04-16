from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from services.attempts.models import AttemptRecord
from services.context.file_excerptor import extract_file_context
from services.context.file_inventory import WorkspaceInventoryBuilder
from services.context.file_selector import SelectedContextFile, select_relevant_files
from services.targeting.models import ScopeContract


@dataclass(frozen=True)
class ContextConfig:
    max_context_files: int = 5
    max_context_chars_total: int = 12000
    max_chars_per_file: int = 3200


@dataclass
class ContextFilePayload:
    relative_path: str
    reason: str
    score: int
    selection_confidence: str
    include_mode: str
    included_chars: int
    metadata: dict
    content: str


@dataclass
class GenerationContextPackage:
    task_summary: str
    attempt_type: str
    project_root: str
    selection_confidence: str
    selected_files: list[ContextFilePayload] = field(default_factory=list)
    editable_targets: list[str] = field(default_factory=list)
    read_only_context_files: list[str] = field(default_factory=list)
    prior_attempt_summary: str = ""
    failure_detail: str = ""
    policy_summary: str = "Respect workspace path safety. Do not use fuzzy patching. Keep changes bounded."


class ContextPackageBuilder:
    def __init__(self, config: ContextConfig | None = None):
        self.config = config or ContextConfig()
        self.inventory_builder = WorkspaceInventoryBuilder()
        self._inventory_cache: dict[str, list] = {}

    def build(
        self,
        project_root: str | Path,
        spec_text: str,
        attempt_type: str,
        prior_history: list[AttemptRecord],
        task_target: str = "",
        scope_contract: ScopeContract | None = None,
    ) -> GenerationContextPackage:
        root = str(Path(project_root).expanduser().resolve())
        inventory = self._inventory_cache.get(root)
        if inventory is None:
            inventory = self.inventory_builder.build(root)
            self._inventory_cache[root] = inventory

        prior_targets = [task_target] if task_target else []
        prior_failure_files = [path for attempt in prior_history for path in attempt.targeted_files if attempt.failure_class]
        selected, confidence = select_relevant_files(
            inventory=inventory,
            spec_text=spec_text,
            prior_targets=prior_targets,
            prior_failure_files=prior_failure_files,
            max_files=self.config.max_context_files,
        )

        total_chars = 0
        payloads: list[ContextFilePayload] = []
        repair_line = 0
        if prior_history:
            repair_line = 0
        for item in selected:
            remaining = self.config.max_context_chars_total - total_chars
            if remaining <= 0:
                break
            excerpt = extract_file_context(
                item.absolute_path,
                spec_text=spec_text,
                max_chars_per_file=min(self.config.max_chars_per_file, remaining),
                repair_line=repair_line,
            )
            total_chars += excerpt.included_chars
            payloads.append(
                ContextFilePayload(
                    relative_path=item.relative_path,
                    reason=item.reason,
                    score=item.score,
                    selection_confidence=item.selection_confidence,
                    include_mode=excerpt.mode,
                    included_chars=excerpt.included_chars,
                    metadata=item.metadata,
                    content=excerpt.content,
                )
            )

        prior_attempt_summary = ""
        failure_detail = ""
        if prior_history:
            prior = prior_history[-1]
            prior_attempt_summary = f"{prior.attempt_type}: {prior.validation_result_summary}"
            failure_detail = prior.error_summary

        return GenerationContextPackage(
            task_summary=spec_text,
            attempt_type=attempt_type,
            project_root=root,
            selection_confidence=confidence,
            selected_files=payloads,
            editable_targets=(scope_contract.editable_files if scope_contract else []),
            read_only_context_files=(scope_contract.read_only_context_files if scope_contract else []),
            prior_attempt_summary=prior_attempt_summary,
            failure_detail=failure_detail,
        )

    def to_prompt_text(self, package: GenerationContextPackage) -> str:
        lines = [
            "[WORKSPACE CONTEXT]",
            f"Project root: {package.project_root}",
            f"Attempt type: {package.attempt_type}",
            f"Selection confidence: {package.selection_confidence}",
            f"Policy: {package.policy_summary}",
            f"Editable targets: {package.editable_targets}",
            f"Read-only context: {package.read_only_context_files}",
        ]
        if package.prior_attempt_summary:
            lines.append(f"Prior attempt: {package.prior_attempt_summary}")
        if package.failure_detail:
            lines.append(f"Failure detail: {package.failure_detail}")
        lines.append("Selected files:")
        for item in package.selected_files:
            lines.append(f"- {item.relative_path} [{item.reason}] mode={item.include_mode} chars={item.included_chars}")
            structure = item.metadata.get("structure") or {}
            if structure:
                funcs = structure.get("functions", [])
                classes = structure.get("classes", [])
                imports = structure.get("imports", [])
                lines.append(f"  imports={imports[:6]} functions={funcs[:6]} classes={classes[:6]}")
            lines.append(item.content)
            lines.append("")
        return "\n".join(lines).strip()

    def to_dict(self, package: GenerationContextPackage) -> dict:
        return asdict(package)

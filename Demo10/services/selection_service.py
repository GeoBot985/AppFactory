from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from services.index_service import ArchitectureIndex, IndexedFile


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "build",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "use",
    "with",
}

PRIMARY_CAP = 4
CONTEXT_CAP = 6
PRIMARY_MIN_SCORE = 4
CONTEXT_MIN_SCORE = 3


@dataclass
class SelectedFile:
    relative_path: str
    selection_score: int
    selection_kind: str
    matched_signals: list[str]
    selection_reason: str
    role_tags: list[str]
    is_test: bool
    is_entrypoint: bool


@dataclass
class SelectionResult:
    project_root: str
    spec_text: str
    selection_started_at: str
    selection_completed_at: str
    status: str
    selected_primary_count: int
    selected_context_count: int
    total_selected_count: int
    unmatched_terms: list[str]
    selection_notes: list[str]
    selected_files: list[SelectedFile] = field(default_factory=list)

    def to_preview_text(self) -> str:
        lines = [
            "{",
            f'  "project_root": "{self.project_root}",',
            f'  "selection_started_at": "{self.selection_started_at}",',
            f'  "selection_completed_at": "{self.selection_completed_at}",',
            f'  "status": "{self.status}",',
            f'  "selected_primary_count": {self.selected_primary_count},',
            f'  "selected_context_count": {self.selected_context_count},',
            f'  "total_selected_count": {self.total_selected_count},',
            f'  "unmatched_terms": {self.unmatched_terms},',
            f'  "selection_notes": {self.selection_notes},',
            '  "selected_files": [',
        ]
        for idx, entry in enumerate(self.selected_files):
            suffix = "," if idx < len(self.selected_files) - 1 else ""
            lines.extend(
                [
                    "    {",
                    f'      "relative_path": "{entry.relative_path}",',
                    f'      "selection_score": {entry.selection_score},',
                    f'      "selection_kind": "{entry.selection_kind}",',
                    f'      "matched_signals": {entry.matched_signals},',
                    f'      "selection_reason": "{entry.selection_reason}",',
                    f'      "role_tags": {entry.role_tags},',
                    f'      "is_test": {str(entry.is_test).lower()},',
                    f'      "is_entrypoint": {str(entry.is_entrypoint).lower()}',
                    f"    }}{suffix}",
                ]
            )
        lines.extend(["  ]", "}"])
        return "\n".join(lines)


class FileSelector:
    def select(self, spec_text: str, architecture_index: ArchitectureIndex, session_context: dict | None = None) -> SelectionResult:
        started = self._now()
        terms = self._tokenize(spec_text)
        scored: list[tuple[int, list[str], IndexedFile]] = []

        failure_files = session_context.get("failure_files", []) if session_context else []
        primary_files = session_context.get("primary_files", []) if session_context else []

        for entry in architecture_index.files:
            score, reasons = self._score_file(entry, terms, architecture_index.files)

            # Session boost
            if entry.relative_path in failure_files:
                score += 5
                reasons.append("recent session failure boost")
            if entry.relative_path in primary_files:
                score += 2
                reasons.append("session working set boost")

            if score > 0:
                scored.append((score, reasons, entry))

        scored.sort(key=lambda item: (-item[0], item[2].relative_path))
        primary = [item for item in scored if item[0] >= PRIMARY_MIN_SCORE][:PRIMARY_CAP]
        primary_paths = {entry.relative_path for _, _, entry in primary}

        context_candidates: list[tuple[int, list[str], IndexedFile]] = []
        for score, reasons, entry in scored:
            if entry.relative_path in primary_paths:
                continue
            if len(context_candidates) >= CONTEXT_CAP:
                break
            expanded_reasons = list(reasons)
            if any(self._is_neighbor(entry, primary_entry) for _, _, primary_entry in primary):
                score += 2
                expanded_reasons.append("dependency or naming adjacency to primary file")
            if score >= CONTEXT_MIN_SCORE:
                context_candidates.append((score, expanded_reasons, entry))

        matched_terms = self._collect_matched_terms(scored, terms)
        unmatched_terms = [term for term in terms if term not in matched_terms]
        selected_files: list[SelectedFile] = []

        for score, reasons, entry in primary:
            selected_files.append(
                SelectedFile(
                    relative_path=entry.relative_path,
                    selection_score=score,
                    selection_kind="primary_editable",
                    matched_signals=reasons,
                    selection_reason=self._reason_text(reasons),
                    role_tags=entry.role_tags,
                    is_test=entry.is_test,
                    is_entrypoint=entry.is_entrypoint,
                )
            )
        for score, reasons, entry in context_candidates:
            selected_files.append(
                SelectedFile(
                    relative_path=entry.relative_path,
                    selection_score=score,
                    selection_kind="secondary_context",
                    matched_signals=reasons,
                    selection_reason=self._reason_text(reasons),
                    role_tags=entry.role_tags,
                    is_test=entry.is_test,
                    is_entrypoint=entry.is_entrypoint,
                )
            )

        notes = [
            f"normalized_terms={len(terms)}",
            f"primary_cap={PRIMARY_CAP}",
            f"context_cap={CONTEXT_CAP}",
        ]
        if not selected_files:
            notes.append("No strong deterministic matches found.")

        return SelectionResult(
            project_root=architecture_index.project_root,
            spec_text=spec_text,
            selection_started_at=started,
            selection_completed_at=self._now(),
            status="completed",
            selected_primary_count=len(primary),
            selected_context_count=len(context_candidates),
            total_selected_count=len(selected_files),
            unmatched_terms=unmatched_terms,
            selection_notes=notes,
            selected_files=selected_files,
        )

    def _score_file(
        self,
        entry: IndexedFile,
        terms: list[str],
        all_files: list[IndexedFile],
    ) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        path_tokens = set(self._tokenize(entry.relative_path))
        module_tokens = set(self._tokenize(entry.module_name))
        symbol_tokens = set(self._tokenize(" ".join(entry.top_level_functions + entry.top_level_classes)))
        role_tokens = set(entry.role_tags)

        for term in terms:
            if term in path_tokens:
                score += 4
                reasons.append(f"matched path/name token {term}")
            if term in module_tokens:
                score += 3
                reasons.append(f"matched module token {term}")
            if term in symbol_tokens:
                score += 4
                reasons.append(f"matched symbol token {term}")
            if term in role_tokens:
                score += 3
                reasons.append(f"matched role tag {term}")
            if self._has_prefix_match(term, path_tokens | module_tokens | symbol_tokens):
                score += 2
                reasons.append(f"matched normalized token family {term}")

        if any(term in {"ui", "screen", "pane", "window"} for term in terms) and "ui" in entry.role_tags:
            score += 3
            reasons.append("ui role boosted by spec terms")
        if any(term in {"service", "index", "build", "selector", "selection"} for term in terms) and "service" in entry.role_tags:
            score += 3
            reasons.append("service role boosted by spec terms")
        if any(term in {"run", "launch", "start", "app"} for term in terms) and entry.is_entrypoint:
            score += 2
            reasons.append("entrypoint boosted due to run/app terms in spec")
        if any(term in {"test", "tests"} for term in terms) and entry.is_test:
            score += 2
            reasons.append("test relevance matched spec terms")

        if entry.is_test and any(not other.is_test and Path(entry.relative_path).stem.replace("test_", "") in other.relative_path for other in all_files):
            score += 1
            reasons.append("likely test partner of source file")

        deduped = list(dict.fromkeys(reasons))
        return score, deduped

    def _collect_matched_terms(self, scored: list[tuple[int, list[str], IndexedFile]], terms: list[str]) -> set[str]:
        matched: set[str] = set()
        for _, reasons, _ in scored:
            for reason in reasons:
                for term in terms:
                    if term in reason:
                        matched.add(term)
        return matched

    def _is_neighbor(self, entry: IndexedFile, primary_entry: IndexedFile) -> bool:
        if any(import_name and primary_entry.module_name.endswith(import_name.split(".")[-1]) for import_name in entry.imports):
            return True
        if any(import_name and entry.module_name.endswith(import_name.split(".")[-1]) for import_name in primary_entry.imports):
            return True
        primary_stem = primary_entry.relative_path.rsplit(".", 1)[0]
        entry_stem = entry.relative_path.rsplit(".", 1)[0]
        return primary_stem in entry_stem or entry_stem in primary_stem

    def _tokenize(self, value: str) -> list[str]:
        cleaned = re.sub(r"[^a-zA-Z0-9_./-]+", " ", value.lower())
        tokens = re.split(r"[\s/._-]+", cleaned)
        return [token for token in tokens if token and token not in STOPWORDS]

    def _has_prefix_match(self, term: str, candidates: set[str]) -> bool:
        if len(term) < 5:
            return False
        stem = term[:6]
        return any(candidate.startswith(stem) or stem.startswith(candidate[:6]) for candidate in candidates if len(candidate) >= 5)

    def _reason_text(self, reasons: list[str]) -> str:
        return "; ".join(reasons[:4]) if reasons else "weak structural match"

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

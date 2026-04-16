from __future__ import annotations

import re
from dataclasses import dataclass

from services.context.file_inventory import InventoryFile


@dataclass
class SelectedContextFile:
    relative_path: str
    absolute_path: str
    reason: str
    score: int
    selection_confidence: str
    metadata: dict


def normalize_terms(text: str) -> list[str]:
    lowered = text.lower()
    tokens = re.findall(r"[a-z0-9_./-]+", lowered)
    stop = {"the", "and", "for", "with", "into", "from", "that", "this", "file", "code", "spec"}
    return [token for token in tokens if token and token not in stop]


def select_relevant_files(
    inventory: list[InventoryFile],
    spec_text: str,
    prior_targets: list[str],
    prior_failure_files: list[str],
    max_files: int,
) -> tuple[list[SelectedContextFile], str]:
    terms = normalize_terms(spec_text)
    explicit_paths = {term for term in terms if "/" in term or "." in term}
    scored: list[tuple[int, str, InventoryFile]] = []

    for item in inventory:
        if not item.is_text:
            continue
        if item.extension not in {"", ".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini"} and item.language == "text":
            continue

        score = 0
        reason = ""
        lower_path = item.relative_path.lower()
        filename = item.relative_path.split("/")[-1].lower()
        dirs = lower_path.split("/")[:-1]

        if any(explicit == lower_path or explicit.endswith(filename) for explicit in explicit_paths):
            score += 100
            reason = "explicit_path_match"
        elif item.relative_path in prior_failure_files:
            score += 90
            reason = "previous_attempt_failure_file"
        elif item.relative_path in prior_targets:
            score += 85
            reason = "previous_attempt_target"
        else:
            overlap = [term for term in terms if term in filename]
            if overlap:
                score += 50 + min(20, len(overlap) * 5)
                reason = "filename_keyword_match"
            else:
                dir_overlap = [term for term in terms if any(term in directory for directory in dirs)]
                if dir_overlap:
                    score += 35 + min(15, len(dir_overlap) * 3)
                    reason = "directory_keyword_match"
                elif item.is_entrypoint:
                    score += 18
                    reason = "entrypoint_candidate"
                elif item.is_config:
                    score += 14
                    reason = "config_candidate"
                elif filename.lower() == "readme.md":
                    score += 12
                    reason = "readme_anchor"

        if item.language == "python" and any(term in {"python", "function", "class", "import", "module"} for term in terms):
            score += 10
            reason = reason or "python_type_relevance"

        if score > 0:
            scored.append((score, reason, item))

    scored.sort(key=lambda row: (-row[0], row[2].relative_path))
    selected = scored[:max_files]
    confidence = "strong" if selected and selected[0][0] >= 50 else "weak"
    results = [
        SelectedContextFile(
            relative_path=item.relative_path,
            absolute_path=item.absolute_path,
            reason=reason,
            score=score,
            selection_confidence=confidence,
            metadata={
                "extension": item.extension,
                "size": item.size,
                "line_count": item.line_count,
                "language": item.language,
                "is_entrypoint": item.is_entrypoint,
                "is_config": item.is_config,
                "structure": item.structure,
            },
        )
        for score, reason, item in selected
    ]
    return results, confidence

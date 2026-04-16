from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.context.file_selector import normalize_terms


@dataclass
class ExcerptResult:
    mode: str
    included_chars: int
    content: str


def extract_file_context(
    path: str | Path,
    spec_text: str,
    max_chars_per_file: int,
    repair_line: int = 0,
) -> ExcerptResult:
    file_path = Path(path)
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = file_path.read_text(encoding="utf-8", errors="replace")

    if len(content) <= max_chars_per_file:
        return ExcerptResult(mode="full", included_chars=len(content), content=content)

    lines = content.splitlines()
    terms = normalize_terms(spec_text)
    candidate_ranges: list[tuple[int, int]] = []

    if repair_line > 0:
        start = max(0, repair_line - 4)
        end = min(len(lines), repair_line + 3)
        candidate_ranges.append((start, end))

    for idx, line in enumerate(lines):
        lowered = line.lower()
        if any(term in lowered for term in terms if len(term) >= 3):
            start = max(0, idx - 3)
            end = min(len(lines), idx + 4)
            candidate_ranges.append((start, end))
            if len(candidate_ranges) >= 4:
                break

    if not candidate_ranges:
        candidate_ranges.append((0, min(len(lines), 80)))

    excerpt_lines: list[str] = []
    seen = set()
    for start, end in candidate_ranges:
        for idx in range(start, end):
            if idx not in seen:
                excerpt_lines.append(lines[idx])
                seen.add(idx)
        excerpt_lines.append("...")
        if len("\n".join(excerpt_lines)) >= max_chars_per_file:
            break

    excerpt = "\n".join(excerpt_lines).strip()
    if len(excerpt) > max_chars_per_file:
        excerpt = excerpt[:max_chars_per_file]
    return ExcerptResult(mode="excerpt", included_chars=len(excerpt), content=excerpt)

from __future__ import annotations

import re
from typing import Optional
from .models import AnchorResolution, AnchorStatus, AnchorMatch, AnchorType, MatchMode
from .block_extractor import get_python_block_boundaries


class AnchorResolver:
    def resolve(self, lines: list[str], anchor_type: AnchorType, anchor_value: str, match_mode: MatchMode = MatchMode.EXACT) -> AnchorResolution:
        if anchor_type == AnchorType.FILE_START:
            return self._resolve_file_boundary(lines, is_start=True)
        if anchor_type == AnchorType.FILE_END:
            return self._resolve_file_boundary(lines, is_start=False)
        if anchor_type == AnchorType.LINE_MATCH:
            return self._resolve_line_match(lines, anchor_value, match_mode)
        if anchor_type == AnchorType.FUNCTION:
            return self._resolve_python_symbol(lines, "def", anchor_value)
        if anchor_type == AnchorType.CLASS:
            return self._resolve_python_symbol(lines, "class", anchor_value)
        if anchor_type == AnchorType.IMPORT:
            return self._resolve_import(lines, anchor_value)
        if anchor_type == AnchorType.REGION_MARKER:
            return self._resolve_region(lines, anchor_value)

        return AnchorResolution(status=AnchorStatus.NOT_FOUND)

    def _resolve_file_boundary(self, lines: list[str], is_start: bool) -> AnchorResolution:
        line_idx = 0 if is_start else max(0, len(lines) - 1)
        content = lines[line_idx] if lines else ""
        match = AnchorMatch(
            start_line=line_idx,
            end_line=line_idx,
            start_char=0,
            end_char=len(content),
            preview=content
        )
        return AnchorResolution(status=AnchorStatus.OK, matches=[match], selected_match=match)

    def _resolve_line_match(self, lines: list[str], value: str, mode: MatchMode) -> AnchorResolution:
        matches = []
        for i, line in enumerate(lines):
            found = False
            if mode == MatchMode.EXACT:
                found = (line.strip() == value.strip())
            elif mode == MatchMode.CONTAINS:
                found = (value in line)
            elif mode == MatchMode.REGEX:
                try:
                    found = bool(re.search(value, line))
                except re.error:
                    found = False

            if found:
                matches.append(AnchorMatch(
                    start_line=i,
                    end_line=i,
                    start_char=0,
                    end_char=len(line),
                    preview=line
                ))

        return self._build_resolution(matches)

    def _resolve_python_symbol(self, lines: list[str], keyword: str, name: str) -> AnchorResolution:
        pattern = re.compile(rf"^\s*{keyword}\s+{re.escape(name)}\b")
        matches = []
        for i, line in enumerate(lines):
            if pattern.match(line):
                start, end = get_python_block_boundaries(lines, i)
                preview = "".join(lines[start:end+1])
                matches.append(AnchorMatch(
                    start_line=start,
                    end_line=end,
                    start_char=0,
                    end_char=len(lines[end]),
                    preview=preview
                ))
        return self._build_resolution(matches)

    def _resolve_import(self, lines: list[str], value: str) -> AnchorResolution:
        # Simple exact line match for now, or match parts of import
        # Spec says: ensure import "from x import y" exists
        normalized_value = self._normalize_import(value)
        matches = []
        for i, line in enumerate(lines):
            if self._normalize_import(line) == normalized_value:
                matches.append(AnchorMatch(
                    start_line=i,
                    end_line=i,
                    start_char=0,
                    end_char=len(line),
                    preview=line
                ))
        return self._build_resolution(matches)

    def _normalize_import(self, line: str) -> str:
        line = line.strip()
        if not (line.startswith("import ") or line.startswith("from ")):
            return ""
        # Remove comments and normalize whitespace
        line = re.sub(r"#.*$", "", line).strip()
        return " ".join(line.split())

    def _resolve_region(self, lines: list[str], name: str) -> AnchorResolution:
        start_pattern = re.compile(rf"^\s*#\s*BEGIN:\s*{re.escape(name)}\b", re.IGNORECASE)
        end_pattern = re.compile(rf"^\s*#\s*END:\s*{re.escape(name)}\b", re.IGNORECASE)

        start_idx = -1
        matches = []

        for i, line in enumerate(lines):
            if start_pattern.match(line):
                start_idx = i
            elif end_pattern.match(line) and start_idx != -1:
                preview = "".join(lines[start_idx : i + 1])
                matches.append(AnchorMatch(
                    start_line=start_idx,
                    end_line=i,
                    start_char=0,
                    end_char=len(line),
                    preview=preview
                ))
                start_idx = -1

        return self._build_resolution(matches)

    def _build_resolution(self, matches: list[AnchorMatch]) -> AnchorResolution:
        if not matches:
            return AnchorResolution(status=AnchorStatus.NOT_FOUND)
        if len(matches) > 1:
            return AnchorResolution(status=AnchorStatus.AMBIGUOUS, matches=matches)
        return AnchorResolution(status=AnchorStatus.OK, matches=matches, selected_match=matches[0])

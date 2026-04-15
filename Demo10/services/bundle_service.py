from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from services.selection_service import SelectedFile, SelectionResult


@dataclass
class BundleFile:
    relative_path: str
    selection_kind: str
    file_content: str
    content_status: str
    included_reason: str


@dataclass
class WorkingSetBundle:
    project_root: str
    source_spec_text: str
    built_at: str
    status: str
    primary_files: list[BundleFile] = field(default_factory=list)
    context_files: list[BundleFile] = field(default_factory=list)
    primary_count: int = 0
    context_count: int = 0
    total_files: int = 0
    total_characters: int = 0
    truncated_or_blocked: bool = False

    def to_preview_text(self) -> str:
        lines = [
            "{",
            f'  "project_root": "{self.project_root}",',
            f'  "built_at": "{self.built_at}",',
            f'  "status": "{self.status}",',
            f'  "primary_count": {self.primary_count},',
            f'  "context_count": {self.context_count},',
            f'  "total_files": {self.total_files},',
            f'  "total_characters": {self.total_characters},',
            f'  "truncated_or_blocked": {str(self.truncated_or_blocked).lower()},',
            '  "primary_files": [',
        ]
        for entry in self.primary_files:
            lines.extend(self._bundle_file_lines(entry, "    "))
        lines.extend(['  ],', '  "context_files": ['])
        for entry in self.context_files:
            lines.extend(self._bundle_file_lines(entry, "    "))
        lines.extend(["  ]", "}"])
        return "\n".join(lines)

    def _bundle_file_lines(self, entry: BundleFile, indent: str) -> list[str]:
        content_preview = entry.file_content.replace("\\", "\\\\").replace('"', "'")
        return [
            f"{indent}{{",
            f'{indent}  "relative_path": "{entry.relative_path}",',
            f'{indent}  "selection_kind": "{entry.selection_kind}",',
            f'{indent}  "content_status": "{entry.content_status}",',
            f'{indent}  "included_reason": "{entry.included_reason}",',
            f'{indent}  "file_content": "{content_preview}"',
            f"{indent}}},",
        ]


class BundleBuilder:
    def build(self, selection_result: SelectionResult) -> WorkingSetBundle:
        project_root = Path(selection_result.project_root)
        primary_files: list[BundleFile] = []
        context_files: list[BundleFile] = []
        total_chars = 0
        truncated = False

        for selected in selection_result.selected_files:
            bundle_file = self._read_selected_file(project_root, selected)
            total_chars += len(bundle_file.file_content)
            if bundle_file.content_status != "included":
                truncated = True
            if selected.selection_kind == "primary_editable":
                primary_files.append(bundle_file)
            else:
                context_files.append(bundle_file)

        return WorkingSetBundle(
            project_root=selection_result.project_root,
            source_spec_text=selection_result.spec_text,
            built_at=datetime.now().isoformat(timespec="seconds"),
            status="completed",
            primary_files=primary_files,
            context_files=context_files,
            primary_count=len(primary_files),
            context_count=len(context_files),
            total_files=len(primary_files) + len(context_files),
            total_characters=total_chars,
            truncated_or_blocked=truncated,
        )

    def _read_selected_file(self, project_root: Path, selected: SelectedFile) -> BundleFile:
        path = project_root / Path(selected.relative_path)
        try:
            raw = path.read_bytes()
        except OSError as exc:
            return BundleFile(
                relative_path=selected.relative_path,
                selection_kind=selected.selection_kind,
                file_content=f"[unreadable] {exc}",
                content_status="blocked",
                included_reason=selected.selection_reason,
            )

        if b"\x00" in raw:
            return BundleFile(
                relative_path=selected.relative_path,
                selection_kind=selected.selection_kind,
                file_content="[binary content omitted]",
                content_status="blocked",
                included_reason=selected.selection_reason,
            )

        text = raw.decode("utf-8", errors="replace")
        if len(text) > 12000:
            text = text[:12000] + "\n\n[truncated]"
            status = "truncated"
        else:
            status = "included"

        return BundleFile(
            relative_path=selected.relative_path,
            selection_kind=selected.selection_kind,
            file_content=text,
            content_status=status,
            included_reason=selected.selection_reason,
        )

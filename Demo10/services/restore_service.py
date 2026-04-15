from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from services.bundle_service import BundleFile, WorkingSetBundle


@dataclass
class RestoreResult:
    project_root: str
    started_at: str
    completed_at: str
    status: str
    attempted_file_count: int
    written_file_count: int
    failed_file_count: int
    skipped_file_count: int
    written_files: list[str] = field(default_factory=list)
    failed_files: list[str] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)

    def to_preview_text(self) -> str:
        return "\n".join(
            [
                "{",
                f'  "project_root": "{self.project_root}",',
                f'  "started_at": "{self.started_at}",',
                f'  "completed_at": "{self.completed_at}",',
                f'  "status": "{self.status}",',
                f'  "attempted_file_count": {self.attempted_file_count},',
                f'  "written_file_count": {self.written_file_count},',
                f'  "failed_file_count": {self.failed_file_count},',
                f'  "skipped_file_count": {self.skipped_file_count},',
                f'  "written_files": {self.written_files},',
                f'  "failed_files": {self.failed_files},',
                f'  "failure_reasons": {self.failure_reasons}',
                "}",
            ]
        )


class RestoreService:
    def preview_bundle(self, bundle: WorkingSetBundle) -> str:
        lines = ["[RESTORE PREVIEW]"]
        for entry in bundle.primary_files + bundle.context_files:
            will_write = entry.content_status in {"included", "truncated"}
            lines.append(
                f"{entry.relative_path} | {entry.selection_kind} | "
                f"{'write' if will_write else 'skip'} | chars={len(entry.file_content)} | status={entry.content_status}"
            )
        return "\n".join(lines)

    def restore_bundle(self, project_root: str | Path, bundle: WorkingSetBundle) -> RestoreResult:
        root = Path(project_root).expanduser().resolve()
        started = self._now()
        written_files: list[str] = []
        failed_files: list[str] = []
        failure_reasons: list[str] = []
        skipped_file_count = 0

        bundle_files = bundle.primary_files + bundle.context_files
        for entry in bundle_files:
            ok, target_or_reason = self._validate_target(root, entry)
            if not ok:
                failed_files.append(entry.relative_path)
                failure_reasons.append(target_or_reason)
                continue

            if entry.content_status not in {"included", "truncated"}:
                skipped_file_count += 1
                continue

            target = Path(target_or_reason)
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(entry.file_content, encoding="utf-8", newline="")
                written_files.append(entry.relative_path)
            except OSError as exc:
                failed_files.append(entry.relative_path)
                failure_reasons.append(f"{entry.relative_path}: {exc}")

        failed_count = len(failed_files)
        written_count = len(written_files)
        status = "completed" if failed_count == 0 else ("failed" if written_count == 0 else "completed_with_failures")
        return RestoreResult(
            project_root=str(root),
            started_at=started,
            completed_at=self._now(),
            status=status,
            attempted_file_count=len(bundle_files),
            written_file_count=written_count,
            failed_file_count=failed_count,
            skipped_file_count=skipped_file_count,
            written_files=written_files,
            failed_files=failed_files,
            failure_reasons=failure_reasons,
        )

    def _validate_target(self, root: Path, entry: BundleFile) -> tuple[bool, str]:
        if not entry.relative_path or entry.file_content is None or not entry.selection_kind:
            return False, f"{entry.relative_path or '(missing path)'}: malformed bundle entry"
        relative = Path(entry.relative_path)
        if relative.is_absolute():
            return False, f"{entry.relative_path}: absolute paths are not allowed"
        target = (root / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return False, f"{entry.relative_path}: path escapes project root"
        return True, str(target)

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

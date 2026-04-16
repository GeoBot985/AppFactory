from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from services.bundle_service import BundleFile, WorkingSetBundle
from services.bundle_edit_service import CandidateBundle, CandidateFile
from services.policy.engine import PolicyEngine
from services.policy.models import PolicyConfig, PolicyDomain, PolicyDecision
from typing import Optional


@dataclass
class FilePreview:
    relative_path: str
    change_type: str  # new, modified, unchanged, skipped
    old_size: int = 0
    new_size: int = 0
    old_line_count: int = 0
    new_line_count: int = 0
    change_summary: str = ""


@dataclass
class RestorePreview:
    project_root: str
    generated_at: str
    files: list[FilePreview] = field(default_factory=list)
    total_files: int = 0
    new_count: int = 0
    modified_count: int = 0
    unchanged_count: int = 0
    skipped_count: int = 0

    def to_preview_text(self) -> str:
        lines = [
            f"Project: {self.project_root}",
            f"Generated: {self.generated_at}",
            f"Summary: total={self.total_files}, new={self.new_count}, modified={self.modified_count}, unchanged={self.unchanged_count}, skipped={self.skipped_count}",
            "",
            f"{'PATH':<50} | {'CHANGE':<10} | {'SIZE (OLD -> NEW)':<20} | {'LINES':<10}",
            "-" * 100
        ]
        for f in self.files:
            size_str = f"{f.old_size} -> {f.new_size}"
            lines.append(f"{f.relative_path[:50]:<50} | {f.change_type:<10} | {size_str:<20} | {f.new_line_count:<10}")
        return "\n".join(lines)


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
    def __init__(self, policy_config: Optional[PolicyConfig] = None):
        self.policy_engine = PolicyEngine(policy_config or PolicyConfig())

    def compute_bundle_preview(self, project_root: str | Path, bundle: WorkingSetBundle) -> RestorePreview:
        root = Path(project_root).expanduser().resolve()
        files_preview: list[FilePreview] = []

        bundle_entries = bundle.primary_files + bundle.context_files
        for entry in bundle_entries:
            fp = self._compute_file_preview(root, entry.relative_path, entry.file_content, entry.content_status)
            files_preview.append(fp)

        return self._summarize_preview(str(root), files_preview)

    def compute_candidate_preview(self, project_root: str | Path, candidate: CandidateBundle) -> RestorePreview:
        root = Path(project_root).expanduser().resolve()
        files_preview: list[FilePreview] = []

        for entry in candidate.files:
            fp = self._compute_file_preview(root, entry.relative_path, entry.file_content, entry.content_status)
            files_preview.append(fp)

        return self._summarize_preview(str(root), files_preview)

    def _compute_file_preview(self, root: Path, relative_path: str, new_content: str, status: str) -> FilePreview:
        target = root / relative_path

        # If it's already blocked or shouldn't be written
        if status not in {"included", "truncated", "ready"}:
            return FilePreview(relative_path=relative_path, change_type="skipped", new_size=len(new_content))

        if not target.exists():
            return FilePreview(
                relative_path=relative_path,
                change_type="new",
                new_size=len(new_content),
                new_line_count=len(new_content.splitlines())
            )

        try:
            old_content = target.read_text(encoding="utf-8", errors="replace")
            old_size = len(old_content)
            old_lines = len(old_content.splitlines())
        except Exception:
            old_content = None
            old_size = 0
            old_lines = 0

        new_size = len(new_content)
        new_lines = len(new_content.splitlines())

        if old_content == new_content:
            change_type = "unchanged"
        else:
            change_type = "modified"

        return FilePreview(
            relative_path=relative_path,
            change_type=change_type,
            old_size=old_size,
            new_size=new_size,
            old_line_count=old_lines,
            new_line_count=new_lines
        )

    def _summarize_preview(self, project_root: str, files: list[FilePreview]) -> RestorePreview:
        preview = RestorePreview(
            project_root=project_root,
            generated_at=self._now(),
            files=files,
            total_files=len(files),
            new_count=sum(1 for f in files if f.change_type == "new"),
            modified_count=sum(1 for f in files if f.change_type == "modified"),
            unchanged_count=sum(1 for f in files if f.change_type == "unchanged"),
            skipped_count=sum(1 for f in files if f.change_type == "skipped"),
        )
        return preview

    def preview_bundle(self, bundle: WorkingSetBundle) -> str:
        lines = ["[RESTORE PREVIEW (LEGACY)]"]
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

        # Policy Check for RESTORE
        policy_context = {
            "has_drift": False, # TODO: determine drift
            "project_root": str(root)
        }
        policy_result = self.policy_engine.evaluate(PolicyDomain.RESTORE, "restore_op", policy_context)
        if policy_result.decision == PolicyDecision.BLOCK.value:
            return RestoreResult(
                project_root=str(root),
                started_at=started,
                completed_at=self._now(),
                status="blocked_by_policy",
                attempted_file_count=0,
                written_file_count=0,
                failed_file_count=0,
                skipped_file_count=0,
                failure_reasons=policy_result.reasons
            )

        written_files: list[str] = []
        failed_files: list[str] = []
        failure_reasons: list[str] = []
        skipped_file_count = 0

        bundle_files = bundle.primary_files + bundle.context_files
        for entry in bundle_files:
            ok, target_or_reason = self._validate_target(root, entry.relative_path, entry.file_content, entry.selection_kind)
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

    def restore_candidate_bundle(self, project_root: str | Path, candidate: CandidateBundle) -> RestoreResult:
        root = Path(project_root).expanduser().resolve()
        started = self._now()
        written_files: list[str] = []
        failed_files: list[str] = []
        failure_reasons: list[str] = []
        skipped_file_count = 0

        for entry in candidate.files:
            ok, target_or_reason = self._validate_target(root, entry.relative_path, entry.file_content, entry.selection_kind)
            if not ok:
                failed_files.append(entry.relative_path)
                failure_reasons.append(target_or_reason)
                continue

            # For candidate bundles, we assume everything in there is intended to be written if it has content
            # and status isn't explicitly blocked (though parser/validator should have caught that)
            if entry.content_status == "blocked":
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
            attempted_file_count=len(candidate.files),
            written_file_count=written_count,
            failed_file_count=failed_count,
            skipped_file_count=skipped_file_count,
            written_files=written_files,
            failed_files=failed_files,
            failure_reasons=failure_reasons,
        )

    def _validate_target(self, root: Path, relative_path: str, file_content: str, selection_kind: str) -> tuple[bool, str]:
        if not relative_path or file_content is None or not selection_kind:
            return False, f"{relative_path or '(missing path)'}: malformed bundle entry"
        relative = Path(relative_path)
        if relative.is_absolute():
            return False, f"{relative_path}: absolute paths are not allowed"
        target = (root / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return False, f"{relative_path}: path escapes project root"
        return True, str(target)

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from services.bundle_service import WorkingSetBundle, BundleFile


@dataclass
class CandidateFile:
    relative_path: str
    file_content: str
    selection_kind: str
    content_status: str


@dataclass
class CandidateBundle:
    files: list[CandidateFile] = field(default_factory=list)


@dataclass
class BundleEditRun:
    run_id: str
    slot_index: int  # -1 if not from a slot
    model_name: str
    spec_text: str
    source_bundle: Optional[WorkingSetBundle]
    assembled_prompt: str = ""
    raw_model_output: str = ""
    candidate_bundle: Optional[CandidateBundle] = None
    validation_status: str = "idle"  # idle, passed, failed
    validation_errors: list[str] = field(default_factory=list)
    restore_status: str = "idle"  # idle, started, completed, failed
    started_at: str = ""
    completed_at: str = ""
    status: str = "idle"  # idle, running, completed, failed


class BundleOutputParser:
    def parse(self, raw_output: str) -> CandidateBundle:
        # Attempt to find JSON block
        json_match = re.search(r"(\{.*\}|\[.*\])", raw_output, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON-like structure found in model output")

        try:
            data = json.loads(json_match.group(1))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse JSON from model output: {exc}")

        if not isinstance(data, dict) or "files" not in data:
            raise ValueError("Root JSON object must contain 'files' array")

        files_data = data["files"]
        if not isinstance(files_data, list):
            raise ValueError("'files' field must be a list")

        candidate_files: list[CandidateFile] = []
        seen_paths: set[str] = set()

        for idx, item in enumerate(files_data):
            if not isinstance(item, dict):
                raise ValueError(f"File entry at index {idx} is not an object")

            rel_path = item.get("relative_path")
            content = item.get("file_content")
            kind = item.get("selection_kind", "primary_editable")
            status = item.get("content_status", "ready")

            if not rel_path or content is None:
                raise ValueError(f"File entry at index {idx} missing 'relative_path' or 'file_content'")

            if rel_path in seen_paths:
                raise ValueError(f"Duplicate file path in output: {rel_path}")

            seen_paths.add(rel_path)
            candidate_files.append(
                CandidateFile(
                    relative_path=rel_path,
                    file_content=content,
                    selection_kind=kind,
                    content_status=status
                )
            )

        return CandidateBundle(files=candidate_files)


class BundleValidator:
    def validate(self, candidate: CandidateBundle, source: Optional[WorkingSetBundle], project_root: str) -> list[str]:
        errors: list[str] = []
        root_path = Path(project_root).resolve()

        # 1. Structure is already largely checked by parser, but we can double check counts
        if not candidate.files:
            errors.append("Candidate bundle contains no files")

        # 2. Safety and Boundedness
        allowed_paths: set[str] = set()
        if source:
            allowed_paths.update(f.relative_path for f in source.primary_files)
            # context files are usually read-only, but let's see if we allow editing them
            # Spec says: "model may operate only on the current bounded bundle"
            # and "updated bundle remains bounded to the bundle-declared working set"
            allowed_paths.update(f.relative_path for f in source.context_files)

        for f in candidate.files:
            # Path safety
            rel_path = f.relative_path
            if Path(rel_path).is_absolute():
                errors.append(f"Absolute path not allowed: {rel_path}")
                continue

            try:
                target_path = (root_path / rel_path).resolve()
                if not str(target_path).startswith(str(root_path)):
                    errors.append(f"Path traversal detected: {rel_path}")
            except Exception as exc:
                errors.append(f"Invalid path {rel_path}: {exc}")
                continue

            # Boundedness
            if source and rel_path not in allowed_paths:
                errors.append(f"File not in original bundle: {rel_path}")

        return errors

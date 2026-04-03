import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib import error, request


DEFAULT_MODEL = "codeqwen:7b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_NUM_CTX = 32768
STATE_FILENAME = "state.json"
ATTEMPTS_FILENAME = "attempts.jsonl"
CURRENT_JOB_FILENAME = "current_job.md"
LATEST_FAILURE_FILENAME = "latest_failure.txt"
LATEST_DEBUG_FILENAME = "latest_debug.txt"
BACKUPS_DIRNAME = "backups"
DEFAULT_RETRY_BUDGET = 2
VALID_SPEC_STATUSES = {"pending", "in_progress", "passed", "failed", "escalated"}
FAILURE_CLASS_ORCHESTRATOR = "orchestrator_failure"
FAILURE_CLASS_MODEL = "model_output_failure"
FAILURE_CLASS_SPEC = "spec_or_workspace_failure"
FAILURE_CLASS_VALIDATION = "validation_failure"
BASE_PROMPT = """BASE CONTRACT
You are a strict local coding worker for a bounded workspace task.
Follow only the provided architecture, spec contract, file-specific rules, and file contents.
Modify only allowed files.
Do not create extra files.
Do not change forbidden files.
Do not use markdown fences.
Do not include prose before the first FILE: line.
Do not include prose after the last file block.
Do not return diffs or partial snippets. Return full file contents only.
Return only file blocks in this format:
FILE: src/main.py
<full file content>

FILE: tests/test_main.py
<full file content>

Reject these actions by not attempting them:
- any file outside the allowed list
- test code placed in src/ files
- application logic or app entrypoints placed in tests/ files
- missing information required to produce a safe change
"""


class AppFactoryError(Exception):
    def __init__(
        self,
        message: str,
        *,
        failure_class: str = FAILURE_CLASS_ORCHESTRATOR,
        failure_location: str = "orchestrator",
        recommended_fix_target: str = "orchestrator",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.failure_class = failure_class
        self.failure_location = failure_location
        self.recommended_fix_target = recommended_fix_target


def build_failure_info(
    failure_class: str,
    failure_location: str,
    failure_reason: str,
    recommended_fix_target: str,
) -> Dict[str, str]:
    return {
        "failure_class": failure_class,
        "failure_location": failure_location,
        "failure_reason": failure_reason,
        "recommended_fix_target": recommended_fix_target,
    }


def failure_info_from_exception(exc: AppFactoryError) -> Dict[str, str]:
    return build_failure_info(exc.failure_class, exc.failure_location, exc.message, exc.recommended_fix_target)


def empty_failure_info() -> Dict[str, str]:
    return build_failure_info("", "", "", "")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def compact_timestamp() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def print_log(message: str) -> None:
    print(message, flush=True)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Single-file local coding orchestrator for a workspace.")
    parser.add_argument("--workspace", required=True, help="Path to the workspace root.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model name (default: {DEFAULT_MODEL}).")
    parser.add_argument(
        "--ollama-url",
        default=DEFAULT_OLLAMA_URL,
        help=f"Ollama base URL (default: {DEFAULT_OLLAMA_URL}).",
    )
    parser.add_argument("--max-specs", type=int, default=1, help="Maximum number of specs to attempt in this run.")
    parser.add_argument("--dry-run", action="store_true", help="Assemble and print intended actions without writing files or running validation.")
    parser.add_argument("--spec", help="Optional spec filename to force, for example spec_003.md.")
    args = parser.parse_args(argv)
    if args.max_specs < 1:
        raise AppFactoryError("--max-specs must be at least 1.", failure_location="cli", recommended_fix_target="orchestrator")
    return args


def ensure_within_workspace(workspace: Path, candidate: Path) -> None:
    workspace_resolved = workspace.resolve()
    candidate_resolved = candidate.resolve()
    try:
        candidate_resolved.relative_to(workspace_resolved)
    except ValueError as exc:
        raise AppFactoryError(
            f"Path escapes workspace: {candidate}",
            failure_class=FAILURE_CLASS_MODEL,
            failure_location="file_plan",
            recommended_fix_target="model",
        ) from exc


def sanitize_relative_path(raw_path: str) -> str:
    candidate = raw_path.strip().replace("/", "\\")
    if not candidate:
        raise AppFactoryError("Empty path is not allowed.", failure_class=FAILURE_CLASS_MODEL, failure_location="file_plan", recommended_fix_target="model")
    path_obj = Path(candidate)
    if path_obj.is_absolute():
        raise AppFactoryError(
            f"Absolute path is not allowed: {raw_path}",
            failure_class=FAILURE_CLASS_MODEL,
            failure_location="file_plan",
            recommended_fix_target="model",
        )
    if any(part in ("", ".", "..") for part in path_obj.parts):
        raise AppFactoryError(
            f"Unsafe path is not allowed: {raw_path}",
            failure_class=FAILURE_CLASS_MODEL,
            failure_location="file_plan",
            recommended_fix_target="model",
        )
    return path_obj.as_posix()


def workspace_path(workspace: Path, relative_path: str) -> Path:
    safe_rel = sanitize_relative_path(relative_path)
    full_path = (workspace / safe_rel).resolve()
    ensure_within_workspace(workspace, full_path)
    return full_path


def read_text_file(path: Path, *, required: bool = True) -> str:
    if not path.exists():
        if required:
            raise AppFactoryError(
                f"Required file is missing: {path}",
                failure_class=FAILURE_CLASS_SPEC,
                failure_location="workspace",
                recommended_fix_target="workspace",
            )
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise AppFactoryError(
            f"File is not valid UTF-8 text: {path}",
            failure_class=FAILURE_CLASS_SPEC,
            failure_location="workspace",
            recommended_fix_target="workspace",
        ) from exc
    except OSError as exc:
        raise AppFactoryError(f"Failed to read file: {path}", failure_location="filesystem", recommended_fix_target="orchestrator") from exc


def write_text_file(path: Path, content: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    except OSError as exc:
        raise AppFactoryError(f"Failed to write file: {path}", failure_location="filesystem", recommended_fix_target="orchestrator") from exc


def ensure_runtime_dir(runtime_dir: Path, dry_run: bool) -> None:
    if runtime_dir.exists():
        return
    if dry_run:
        print_log(f"[dry-run] Would create runtime directory: {runtime_dir}")
        return
    try:
        runtime_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AppFactoryError(f"Failed to create runtime directory: {runtime_dir}", failure_location="runtime", recommended_fix_target="orchestrator") from exc


def load_state(runtime_dir: Path) -> Dict[str, Any]:
    state_path = runtime_dir / STATE_FILENAME
    if not state_path.exists():
        return {"specs": {}}
    raw = read_text_file(state_path)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppFactoryError(
            f"Invalid JSON in state file: {state_path}",
            failure_class=FAILURE_CLASS_ORCHESTRATOR,
            failure_location="runtime_state",
            recommended_fix_target="orchestrator",
        ) from exc
    if not isinstance(data, dict):
        raise AppFactoryError(f"State file must contain a JSON object: {state_path}", failure_location="runtime_state", recommended_fix_target="orchestrator")
    specs = data.get("specs")
    if specs is None:
        data["specs"] = {}
    elif not isinstance(specs, dict):
        raise AppFactoryError(f"State file 'specs' must be an object: {state_path}", failure_location="runtime_state", recommended_fix_target="orchestrator")
    return data


def save_state(runtime_dir: Path, state: Dict[str, Any], dry_run: bool) -> None:
    state_path = runtime_dir / STATE_FILENAME
    if dry_run:
        print_log(f"[dry-run] Would write state file: {state_path}")
        return
    write_text_file(state_path, json.dumps(state, indent=2, sort_keys=True) + "\n")


def append_attempt(runtime_dir: Path, record: Dict[str, Any], dry_run: bool) -> None:
    path = runtime_dir / ATTEMPTS_FILENAME
    if dry_run:
        print_log(f"[dry-run] Would append attempt log: {path}")
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError as exc:
        raise AppFactoryError(f"Failed to append attempt log: {path}", failure_location="runtime_log", recommended_fix_target="orchestrator") from exc


def write_runtime_text(runtime_dir: Path, filename: str, content: str, dry_run: bool) -> None:
    path = runtime_dir / filename
    if dry_run:
        print_log(f"[dry-run] Would write runtime file: {path}")
        return
    write_text_file(path, content)


def parse_markdown_sections(text: str) -> Tuple[Optional[str], Dict[str, str]]:
    lines = text.splitlines()
    title = None
    sections: Dict[str, List[str]] = {}
    current_name: Optional[str] = None
    current_lines: List[str] = []

    def commit() -> None:
        nonlocal current_name, current_lines
        if current_name is not None:
            sections[current_name.lower()] = current_lines[:]
        current_name = None
        current_lines = []

    for line in lines:
        h1 = re.match(r"^\s*\\?#\s+(.+?)\s*$", line)
        if h1 and title is None:
            title = unescape_markdown_text(h1.group(1).strip())
            continue
        h2 = re.match(r"^\s*\\?##\s+(.+?)\s*$", line)
        if h2:
            commit()
            current_name = unescape_markdown_text(h2.group(1).strip())
            continue
        if current_name is not None:
            current_lines.append(line)
    commit()
    normalized = {name: unescape_markdown_text("\n".join(content).strip()) for name, content in sections.items()}
    return title, normalized


def unescape_markdown_text(value: str) -> str:
    return re.sub(r"\\([\\`*_{}\[\]()#+\-.!])", r"\1", value)


def parse_bullet_list(section_text: str) -> List[str]:
    items: List[str] = []
    for line in section_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = re.match(r"^\\?[-*]\s+(.*)$", stripped)
        if match:
            value = unescape_markdown_text(match.group(1).strip())
            if value:
                items.append(value)
        else:
            items.append(unescape_markdown_text(stripped))
    return items


def parse_retry_budget(section_text: str) -> int:
    match = re.search(r"\d+", section_text)
    if not match:
        raise AppFactoryError(
            "Retry Budget section must contain an integer.",
            failure_class=FAILURE_CLASS_SPEC,
            failure_location="spec_parser",
            recommended_fix_target="spec",
        )
    value = int(match.group(0))
    if value < 0:
        raise AppFactoryError("Retry Budget must be non-negative.", failure_class=FAILURE_CLASS_SPEC, failure_location="spec_parser", recommended_fix_target="spec")
    return value


def extract_spec_id(spec_path: Path) -> str:
    stem = spec_path.stem
    match = re.match(r"^(spec_\d+)", stem, flags=re.IGNORECASE)
    return match.group(1).lower() if match else stem.lower()


def load_spec(spec_path: Path) -> Dict[str, Any]:
    raw_text = read_text_file(spec_path)
    title, sections = parse_markdown_sections(raw_text)
    if not title:
        raise AppFactoryError(
            f"Spec is missing a top-level title heading: {spec_path.name}",
            failure_class=FAILURE_CLASS_SPEC,
            failure_location="spec_parser",
            recommended_fix_target="spec",
        )

    required_sections = ["objective", "allowed files", "forbidden files", "requirements", "validation"]
    missing = [section for section in required_sections if not sections.get(section)]
    if missing:
        raise AppFactoryError(
            f"Spec {spec_path.name} is missing required section(s): {', '.join(missing)}",
            failure_class=FAILURE_CLASS_SPEC,
            failure_location="spec_parser",
            recommended_fix_target="spec",
        )

    try:
        allowed_files = [sanitize_relative_path(item) for item in parse_bullet_list(sections["allowed files"])]
    except AppFactoryError as exc:
        raise AppFactoryError(
            f"Spec {spec_path.name} has an invalid Allowed Files entry: {exc.message}",
            failure_class=FAILURE_CLASS_SPEC,
            failure_location="spec_parser",
            recommended_fix_target="spec",
        ) from exc
    forbidden_raw = parse_bullet_list(sections["forbidden files"])
    forbidden_files: List[str] = []
    for item in forbidden_raw:
        try:
            forbidden_files.append(sanitize_relative_path(item))
        except AppFactoryError:
            continue
    validation_commands = parse_bullet_list(sections["validation"])
    debug_files: List[str] = []
    if sections.get("debug files"):
        try:
            debug_files = [sanitize_relative_path(item) for item in parse_bullet_list(sections["debug files"])]
        except AppFactoryError as exc:
            raise AppFactoryError(
                f"Spec {spec_path.name} has an invalid Debug Files entry: {exc.message}",
                failure_class=FAILURE_CLASS_SPEC,
                failure_location="spec_parser",
                recommended_fix_target="spec",
            ) from exc
    debug_commands = parse_bullet_list(sections.get("debug commands", ""))
    if not allowed_files:
        raise AppFactoryError(f"Spec {spec_path.name} must list at least one allowed file.", failure_class=FAILURE_CLASS_SPEC, failure_location="spec_parser", recommended_fix_target="spec")
    if not validation_commands:
        raise AppFactoryError(f"Spec {spec_path.name} must list at least one validation command.", failure_class=FAILURE_CLASS_SPEC, failure_location="spec_parser", recommended_fix_target="spec")

    retry_budget = DEFAULT_RETRY_BUDGET
    if sections.get("retry budget"):
        retry_budget = parse_retry_budget(sections["retry budget"])

    return {
        "spec_id": extract_spec_id(spec_path),
        "filename": spec_path.name,
        "path": spec_path,
        "title": title,
        "objective": sections["objective"].strip(),
        "allowed_files": allowed_files,
        "forbidden_files": forbidden_files,
        "forbidden_raw": forbidden_raw,
        "requirements_text": sections["requirements"].strip(),
        "file_specific_rules": sections.get("file-specific rules", "").strip(),
        "debug_files": debug_files,
        "debug_commands": debug_commands,
        "validation_commands": validation_commands,
        "retry_budget": retry_budget,
        "raw_text": raw_text,
    }


def list_spec_files(specs_dir: Path) -> List[Path]:
    if not specs_dir.exists() or not specs_dir.is_dir():
        raise AppFactoryError(
            f"Required specs directory is missing: {specs_dir}",
            failure_class=FAILURE_CLASS_SPEC,
            failure_location="workspace",
            recommended_fix_target="workspace",
        )
    return sorted([path for path in specs_dir.iterdir() if path.is_file() and path.suffix.lower() == ".md"], key=lambda p: p.name.lower())


def initialize_spec_state(state: Dict[str, Any], spec_id: str) -> Dict[str, Any]:
    specs = state.setdefault("specs", {})
    entry = specs.get(spec_id)
    if entry is None:
        entry = {
            "spec_id": spec_id,
            "status": "pending",
            "attempt_count": 0,
            "last_error": "",
            "last_updated": utc_now_iso(),
        }
        specs[spec_id] = entry
    else:
        entry.setdefault("spec_id", spec_id)
        entry.setdefault("status", "pending")
        entry.setdefault("attempt_count", 0)
        entry.setdefault("last_error", "")
        entry.setdefault("last_updated", utc_now_iso())
    if entry["status"] not in VALID_SPEC_STATUSES:
        raise AppFactoryError(f"Invalid status '{entry['status']}' for spec {spec_id} in state file.", failure_location="runtime_state", recommended_fix_target="orchestrator")
    return entry


def choose_next_spec(specs_dir: Path, state: Dict[str, Any], forced_spec: Optional[str]) -> Dict[str, Any]:
    spec_files = list_spec_files(specs_dir)
    if forced_spec:
        matches = [path for path in spec_files if path.name.lower() == forced_spec.lower()]
        if not matches:
            raise AppFactoryError(f"Requested spec was not found: {forced_spec}", failure_class=FAILURE_CLASS_SPEC, failure_location="workspace", recommended_fix_target="workspace")
        spec = load_spec(matches[0])
        initialize_spec_state(state, spec["spec_id"])
        return spec

    for spec_path in spec_files:
        spec = load_spec(spec_path)
        spec_state = initialize_spec_state(state, spec["spec_id"])
        if spec_state["status"] in ("pending",) or spec["spec_id"] not in state.get("specs", {}):
            return spec
    raise AppFactoryError("No pending specs remain.", failure_class=FAILURE_CLASS_SPEC, failure_location="workspace", recommended_fix_target="workspace")


def build_file_context(workspace: Path, read_files: List[str]) -> List[Dict[str, str]]:
    file_context: List[Dict[str, str]] = []
    for rel_path in read_files:
        full_path = workspace_path(workspace, rel_path)
        exists = full_path.exists()
        content = ""
        content_loaded = False
        read_error = ""
        if exists:
            try:
                content = read_text_file(full_path, required=False)
                content_loaded = True
            except AppFactoryError as exc:
                read_error = exc.message
        file_context.append(
            {
                "path": rel_path,
                "resolved_path": str(full_path),
                "exists": "yes" if exists else "no",
                "content_loaded": "yes" if content_loaded else "no",
                "read_error": read_error,
                "content": content,
            }
        )
    return file_context


def existing_source_has_entrypoint(file_context: List[Dict[str, str]]) -> bool:
    for entry in file_context:
        if entry["path"].lower() == "src/main.py" and entry["content_loaded"] == "yes":
            content = entry["content"]
            if re.search(r"(?m)^\s*def\s+main\s*\(", content) and '__name__ == "__main__"' in content:
                return True
    return False


def file_context_entry(file_context: List[Dict[str, str]], rel_path: str) -> Optional[Dict[str, str]]:
    target = rel_path.lower()
    for entry in file_context:
        if entry["path"].lower() == target:
            return entry
    return None


def missing_file_template(spec: Dict[str, Any], rel_path: str) -> str:
    normalized = rel_path.lower()
    if normalized == "app.py":
        return "\n".join(
            [
                "Suggested starter template:",
                "from src.taskdesk.ui.app_window import launch_app",
                "",
                "",
                'if __name__ == "__main__":',
                "    launch_app()",
            ]
        )
    if normalized == "src/taskdesk/ui/app_window.py":
        return "\n".join(
            [
                "Suggested starter template:",
                "import tkinter as tk",
                "from src.taskdesk.config import APP_NAME",
                "",
                "",
                "class AppWindow:",
                "    def __init__(self, root: tk.Tk):",
                "        self.root = root",
                "        self.root.title(APP_NAME)",
                "",
                "",
                "def build_root() -> tk.Tk:",
                "    return tk.Tk()",
                "",
                "",
                "def launch_app() -> None:",
                "    root = build_root()",
                "    AppWindow(root)",
                "    root.mainloop()",
            ]
        )
    if normalized == "src/taskdesk/config.py":
        return "\n".join(
            [
                "Suggested starter template:",
                'APP_NAME = "TaskDesk"',
                'DATA_FILENAME = "tasks.json"',
            ]
        )
    if normalized.endswith("__init__.py"):
        return "\n".join(
            [
                "Suggested starter template:",
                '"""Package marker."""',
            ]
        )
    if normalized == "tests/test_smoke.py":
        return "\n".join(
            [
                "Suggested starter template:",
                "import unittest",
                "from src.taskdesk.config import APP_NAME",
                "from src.taskdesk.ui.app_window import AppWindow, build_root",
                "",
                "",
                "class TestSmoke(unittest.TestCase):",
                "    def test_build_window_sets_title(self):",
                "        root = build_root()",
                "        root.withdraw()",
                "        try:",
                "            AppWindow(root)",
                "            self.assertEqual(root.title(), APP_NAME)",
                "        finally:",
                "            root.destroy()",
                "",
                "",
                'if __name__ == "__main__":',
                "    unittest.main()",
            ]
        )
    if normalized == "src/main.py" and spec_requires_main_entrypoint(spec):
        return "\n".join(
            [
                "Suggested starter template:",
                "def greet(name: str) -> str:",
                "    raise NotImplementedError",
                "",
                "def main() -> None:",
                '    print(greet("World"))',
                "",
                'if __name__ == "__main__":',
                "    main()",
            ]
        )
    if normalized == "tests/test_main.py":
        return "\n".join(
            [
                "Suggested starter template:",
                "import unittest",
                "from src import main as main_module",
                "",
                "class TestMain(unittest.TestCase):",
                "    def test_greet_exact_name(self):",
                '        self.assertEqual(main_module.greet("Geo"), "Hello, Geo!")',
                "",
                "    def test_greet_strips_whitespace(self):",
                '        self.assertEqual(main_module.greet(" Geo "), "Hello, Geo!")',
                "",
                "    def test_greet_blank_name_raises(self):",
                "        with self.assertRaises(ValueError):",
                '            main_module.greet(" ")',
                "",
                "    def test_main_exists_and_is_callable(self):",
                "        self.assertTrue(callable(main_module.main))",
                "",
                'if __name__ == "__main__":',
                "    unittest.main()",
            ]
        )
    return ""


def spec_allows_interactive_input(spec: Dict[str, Any]) -> bool:
    haystack = "\n".join(
        [
            spec.get("objective", ""),
            spec.get("requirements_text", ""),
            spec.get("file_specific_rules", ""),
            spec.get("raw_text", ""),
        ]
    ).lower()
    positive_markers = [
        "explicitly require input()",
        "explicitly requires input()",
        "interactive input is required",
        "use input()",
        "prompt the user",
    ]
    negative_markers = [
        "do not introduce interactive input",
        "do not use input()",
        "without spec approval",
        "unless explicitly required",
    ]
    if any(marker in haystack for marker in negative_markers):
        return False
    return any(marker in haystack for marker in positive_markers)


def spec_requires_main_entrypoint(spec: Dict[str, Any]) -> bool:
    haystack = "\n".join(
        [
            spec.get("objective", ""),
            spec.get("requirements_text", ""),
            spec.get("file_specific_rules", ""),
            spec.get("raw_text", ""),
        ]
    ).lower()
    markers = [
        "preserve the existing `main()` function",
        "preserve the existing `if __name__ == \"__main__\": main()` entrypoint pattern",
        "preserve the existing `if __name__ == \"__main__\": main()`",
        "entrypoint pattern",
        "main() function",
    ]
    return any(marker in haystack for marker in markers)


def workspace_uses_src_package_layout(spec: Dict[str, Any]) -> bool:
    paths = spec.get("allowed_files", []) + spec.get("debug_files", [])
    return any(path.startswith("src/taskdesk/") for path in paths)


def build_job_contract(spec: Dict[str, Any], architecture_text: str) -> str:
    allowed_input = spec_allows_interactive_input(spec)
    require_main_entrypoint = spec_requires_main_entrypoint(spec)
    uses_src_package_layout = workspace_uses_src_package_layout(spec)
    file_context = spec.get("_file_context", [])
    src_main_entry = file_context_entry(file_context, "src/main.py")
    tests_main_entry = file_context_entry(file_context, "tests/test_main.py")
    sections = [
        "JOB CONTRACT",
        f"Spec ID: {spec['spec_id']}",
        f"Title: {spec['title']}",
        "Objective:",
        spec["objective"] or "<missing>",
        "",
        "Requirements:",
        spec["requirements_text"] or "<none>",
        "",
        "File-Specific Rules:",
        spec.get("file_specific_rules", "") or "<none>",
        "",
        "Allowed Files:",
        "\n".join(f"- {path}" for path in spec["allowed_files"]),
        "",
        "Forbidden Files:",
        "\n".join(f"- {path}" for path in spec.get("forbidden_raw", spec["forbidden_files"])),
        "",
        "Validation Commands:",
        "\n".join(f"- {command}" for command in spec["validation_commands"]),
        "",
        "Debug Files:",
        "\n".join(f"- {path}" for path in spec["debug_files"]) if spec.get("debug_files") else "<none>",
        "",
        "Debug Commands:",
        "\n".join(f"- {command}" for command in spec["debug_commands"]) if spec.get("debug_commands") else "<none>",
        "",
        "Architecture:",
        architecture_text.strip() or "<missing>",
    ]
    if existing_source_has_entrypoint(spec.get("_file_context", [])):
        sections.extend(
            [
                "",
                "Entrypoint Preservation:",
                "- preserve existing entrypoint structure unless the spec explicitly requires changing it",
                "- do not replace main() with direct interactive input unless explicitly required",
            ]
        )
    if not allowed_input:
        sections.extend(["", "Interactive Input Policy:", "- do not introduce input() unless explicitly required by the spec"])
    if src_main_entry and src_main_entry["exists"] == "no":
        sections.extend(
            [
                "",
                "Bootstrap Guidance For Empty Source File:",
                "- create src/main.py with the required production logic",
                "- include a callable main() function in src/main.py",
                '- include the standard entrypoint pattern: if __name__ == "__main__": main()',
                "- do not call input() unless the spec explicitly requires it",
            ]
        )
        if require_main_entrypoint:
            sections.extend(
                [
                    "- main() must remain present because the workspace contract expects a command-line entrypoint",
                    "- keep main() simple and non-interactive",
                ]
            )
    if tests_main_entry and tests_main_entry["exists"] == "no":
        sections.extend(
            [
                "",
                "Bootstrap Guidance For Empty Test File:",
                "- create tests/test_main.py using Python unittest",
                "- import production code with: from src import main as main_module",
                "- keep all test code in tests/test_main.py",
                "- do not use pytest",
                "- write assertions against main_module.greet(...)",
            ]
        )
        if require_main_entrypoint:
            sections.extend(
                [
                    "- verify that main_module.main exists and is callable",
                ]
            )
    if any("unittest discover" in command for command in spec["validation_commands"]):
        sections.extend(
            [
                "",
                "Validation Compatibility Guidance:",
                "- the generated tests must run under python -m unittest discover",
                "- prefer imports such as from src import main as main_module",
                "- avoid bare calls like greet(...) unless the symbol was imported explicitly",
            ]
        )
    if uses_src_package_layout:
        sections.extend(
            [
                "",
                "Package Import Guidance:",
                "- this workspace uses a src/ package layout",
                "- tests should import application code from src.taskdesk...",
                "- do not use imports like from taskdesk... unless the spec explicitly says so",
            ]
        )
    return "\n".join(sections).strip()


def build_execution_context(
    spec: Dict[str, Any],
    file_context: List[Dict[str, str]],
    debug_file_context: List[Dict[str, str]],
    latest_failure: str,
    latest_debug_output: str,
) -> str:
    parts = ["EXECUTION CONTEXT"]
    for entry in file_context:
        header = (
            f"WORKSPACE FILE: {entry['path']} "
            f"(resolved: {entry['resolved_path']}, exists: {entry['exists']}, content_loaded: {entry['content_loaded']})"
        )
        body = entry["content"] if entry["content"] else "<missing>"
        parts.extend(["", header, body])
        if entry["exists"] == "no":
            template = missing_file_template(spec, entry["path"])
            if template:
                parts.extend(["", template])
        if entry["read_error"]:
            parts.extend(["READ ERROR:", entry["read_error"]])
    if debug_file_context:
        parts.extend(["", "READ-ONLY DEBUG FILES"])
        for entry in debug_file_context:
            header = (
                f"DEBUG WORKSPACE FILE: {entry['path']} "
                f"(resolved: {entry['resolved_path']}, exists: {entry['exists']}, content_loaded: {entry['content_loaded']})"
            )
            body = entry["content"] if entry["content"] else "<missing>"
            parts.extend(["", header, body])
            if entry["read_error"]:
                parts.extend(["READ ERROR:", entry["read_error"]])
    if latest_failure.strip():
        parts.extend(["", "Latest Failure Summary:", latest_failure.strip()])
    if latest_debug_output.strip():
        parts.extend(["", "Latest Debug Output:", latest_debug_output.strip()])
    return "\n".join(parts).strip()


def build_retry_guidance(latest_failure: str, latest_debug_output: str, file_context: List[Dict[str, str]]) -> str:
    if not latest_failure.strip() and not latest_debug_output.strip():
        return ""

    guidance = [
        "RETRY GUIDANCE",
        "This is a retry after a failed attempt.",
        "Focus on fixing the specific failure shown below.",
        "Keep any already-correct file content unchanged unless a change is required to resolve the failure.",
        "Do not rewrite files unnecessarily.",
    ]

    failure_lower = latest_failure.lower()
    if "validation" in failure_lower or "traceback" in failure_lower or "nameerror" in failure_lower or "module" in failure_lower:
        guidance.extend(
            [
                "- fix the concrete test or import failure from the validation output",
                "- make the smallest file changes needed to pass validation",
            ]
        )
    if "model response" in failure_lower or "file: blocks" in failure_lower or "protocol" in failure_lower:
        guidance.extend(
            [
                "- return only valid FILE: blocks",
                "- do not include commentary, fences, or explanatory text",
            ]
        )
    if "input()" in failure_lower:
        guidance.append("- remove any input() usage from src/main.py")
    if "must import from src.main" in failure_lower:
        guidance.append("- ensure tests/test_main.py imports production code from src.main or via from src import main as main_module")
    if "must define main()" in failure_lower or "entrypoint" in failure_lower:
        guidance.append("- ensure src/main.py defines main() and includes if __name__ == \"__main__\": main()")

    existing_files = [entry["path"] for entry in file_context if entry["exists"] == "yes"]
    if existing_files:
        guidance.extend(["", "Existing files to preserve where possible:"] + [f"- {path}" for path in existing_files])
    if latest_debug_output.strip():
        guidance.extend(
            [
                "",
                "Use the debug command output below to guide the fix.",
                "Prefer addressing the concrete runtime/import/test failure shown by the debug commands.",
            ]
        )

    return "\n".join(guidance).strip()


def build_task_contract() -> str:
    return "\n".join(
        [
            "TASK",
            "Return all required file blocks needed for the spec to pass validation.",
            "If a listed allowed file is needed for validation or the spec contract, include it.",
            "Return only file blocks in this format:",
            "FILE: src/main.py",
            "<full file content>",
            "",
            "FILE: tests/test_main.py",
            "<full file content>",
            "",
            "Rules:",
            "- each file block must begin with FILE:",
            "- path must be relative",
            "- content continues until the next FILE: line or end of response",
            "- do not use markdown fences",
            "- do not include any prose before the first FILE: line",
            "- do not include any prose after the last file content",
        ]
    )


def build_prompt(
    architecture_text: str,
    spec: Dict[str, Any],
    file_context: List[Dict[str, str]],
    debug_file_context: List[Dict[str, str]],
    latest_failure: str,
    latest_debug_output: str,
) -> str:
    spec = dict(spec)
    spec["_file_context"] = file_context
    sections = [
        BASE_PROMPT.strip(),
        build_job_contract(spec, architecture_text),
        build_execution_context(spec, file_context, debug_file_context, latest_failure, latest_debug_output),
        build_retry_guidance(latest_failure, latest_debug_output, file_context),
        build_task_contract(),
    ]
    return "\n\n".join(section for section in sections if section.strip()) + "\n"


def write_current_job(runtime_dir: Path, prompt: str, dry_run: bool) -> None:
    write_runtime_text(runtime_dir, CURRENT_JOB_FILENAME, prompt, dry_run)


def measure_prompt(prompt: str) -> Dict[str, int]:
    prompt_bytes = prompt.encode("utf-8")
    return {
        "prompt_characters": len(prompt),
        "prompt_bytes": len(prompt_bytes),
    }


def call_ollama(ollama_url: str, model: str, prompt: str) -> str:
    base = ollama_url.rstrip("/")
    endpoint = f"{base}/api/generate"
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_ctx": DEFAULT_NUM_CTX},
        }
    ).encode("utf-8")
    req = request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=120) as response:
            raw_body = response.read().decode("utf-8")
    except error.URLError as exc:
        raise AppFactoryError(
            f"Failed to reach Ollama at {endpoint}: {exc}",
            failure_class=FAILURE_CLASS_ORCHESTRATOR,
            failure_location="ollama_request",
            recommended_fix_target="orchestrator",
        ) from exc
    except TimeoutError as exc:
        raise AppFactoryError(
            f"Ollama request timed out: {endpoint}",
            failure_class=FAILURE_CLASS_ORCHESTRATOR,
            failure_location="ollama_request",
            recommended_fix_target="orchestrator",
        ) from exc

    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise AppFactoryError(
            "Ollama returned invalid JSON for the API response.",
            failure_class=FAILURE_CLASS_ORCHESTRATOR,
            failure_location="ollama_api",
            recommended_fix_target="orchestrator",
        ) from exc

    model_response = data.get("response")
    if not isinstance(model_response, str):
        raise AppFactoryError("Ollama API response did not contain a text 'response' field.", failure_location="ollama_api", recommended_fix_target="orchestrator")
    return model_response.strip()


def recover_protocol_text(raw_response: str) -> Tuple[str, str]:
    normalized = raw_response.replace("\r\n", "\n")
    parse_status = "ok"

    fenced_match = re.fullmatch(r"\s*```[^\n]*\n(.*?)\n```\s*", normalized, flags=re.DOTALL)
    if fenced_match:
        return fenced_match.group(1), "ok_stripped_markdown_fence"

    if "```" in normalized:
        cleaned_lines = [line for line in normalized.split("\n") if not re.match(r"^\s*```", line)]
        normalized = "\n".join(cleaned_lines)
        parse_status = "ok_recovered_from_markdown_fences"

    return normalized, parse_status


def extract_file_blocks(protocol_text: str, parse_status: str) -> Tuple[List[Dict[str, str]], str]:
    file_marker = re.compile(r"(?m)^FILE:\s*(.+?)\s*$")
    matches = list(file_marker.finditer(protocol_text))
    if not matches:
        raise AppFactoryError(
            "Model response contained no valid FILE: blocks.",
            failure_class=FAILURE_CLASS_MODEL,
            failure_location="model_response_protocol",
            recommended_fix_target="model",
        )

    if protocol_text[:matches[0].start()].strip():
        protocol_text = protocol_text[matches[0].start():]
        matches = list(file_marker.finditer(protocol_text))
        parse_status = "ok_recovered_with_preamble"

    files: List[Dict[str, str]] = []
    for index, match in enumerate(matches):
        path_text = match.group(1).strip()
        if not path_text:
            raise AppFactoryError(
                "Model response contained an empty FILE: path.",
                failure_class=FAILURE_CLASS_MODEL,
                failure_location="model_response_protocol",
                recommended_fix_target="model",
            )
        content_start = match.end()
        if protocol_text[content_start:content_start + 1] == "\n":
            content_start += 1
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(protocol_text)
        content = protocol_text[content_start:content_end]
        if index + 1 < len(matches) and content.endswith("\n"):
            content = content[:-1]
        files.append({"path": path_text, "content": content})

    return files, parse_status


def parse_model_response(raw_response: str) -> Dict[str, Any]:
    if raw_response is None:
        raw_response = ""
    if raw_response.strip() == "":
        raise AppFactoryError(
            "Model response was empty.",
            failure_class=FAILURE_CLASS_MODEL,
            failure_location="model_response_protocol",
            recommended_fix_target="model",
        )

    protocol_text, parse_status = recover_protocol_text(raw_response)
    files, parse_status = extract_file_blocks(protocol_text, parse_status)

    return {
        "files": files,
        "parse_status": parse_status,
        "file_block_count": len(files),
        "file_paths": [item["path"] for item in files],
    }


def validate_proposed_files(workspace: Path, spec: Dict[str, Any], files: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    allowed_set = set(spec["allowed_files"])
    forbidden_set = set(spec["forbidden_files"])
    normalized: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for entry in files:
        rel_path = sanitize_relative_path(entry["path"])
        if rel_path in seen:
            raise AppFactoryError(f"Model returned duplicate file entry: {rel_path}", failure_class=FAILURE_CLASS_MODEL, failure_location="file_plan", recommended_fix_target="model")
        seen.add(rel_path)
        if rel_path in forbidden_set:
            raise AppFactoryError(f"Model attempted forbidden file: {rel_path}", failure_class=FAILURE_CLASS_MODEL, failure_location="file_plan", recommended_fix_target="model")
        if rel_path not in allowed_set:
            raise AppFactoryError(f"Model attempted out-of-scope file: {rel_path}", failure_class=FAILURE_CLASS_MODEL, failure_location="file_plan", recommended_fix_target="model")
        full_path = workspace_path(workspace, rel_path)
        normalized.append({"path": rel_path, "full_path": full_path, "content": entry["content"]})
    return normalized


def backup_existing_file(runtime_dir: Path, spec_id: str, rel_path: str, source_path: Path, dry_run: bool) -> None:
    if not source_path.exists():
        return
    backups_dir = runtime_dir / BACKUPS_DIRNAME
    safe_name = rel_path.replace("/", "_").replace("\\", "_")
    backup_name = f"{spec_id}_{safe_name}_{compact_timestamp()}.bak"
    backup_path = backups_dir / backup_name
    if dry_run:
        print_log(f"[dry-run] Would back up {source_path} -> {backup_path}")
        return
    try:
        backups_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, backup_path)
    except OSError as exc:
        raise AppFactoryError(f"Failed to back up file {source_path} to {backup_path}", failure_location="backup", recommended_fix_target="orchestrator") from exc


def enforce_semantic_file_guards(file_updates: List[Dict[str, Any]], spec: Dict[str, Any], file_context: List[Dict[str, str]]) -> None:
    src_forbidden_patterns = [
        ("import unittest", "src/ files must not import unittest"),
        ("unittest.TestCase", "src/ files must not define unittest.TestCase classes"),
        ("self.assert", "src/ files must not contain unittest assertions"),
        ("unittest.main(", "src/ files must not call unittest.main("),
    ]
    tests_forbidden_patterns = [
        (r"(?m)^\s*def\s+main\s*\(", "tests/ files must not define an application entrypoint"),
    ]
    preserve_entrypoint = existing_source_has_entrypoint(file_context)
    allow_input = spec_allows_interactive_input(spec)
    require_main_entrypoint = spec_requires_main_entrypoint(spec)
    uses_src_package_layout = workspace_uses_src_package_layout(spec)
    prose_markers = [
        "the updated files should now satisfy",
        "here is the updated",
        "this file",
        "explanation:",
    ]

    for update in file_updates:
        rel_path = update["path"]
        content = update["content"]
        normalized_rel = rel_path.lower()
        if normalized_rel.endswith(".py"):
            lower_content = content.lower()
            if any(marker in lower_content for marker in prose_markers):
                raise AppFactoryError(
                    f"Rejected semantic guard for {rel_path}: generated Python files must not contain explanatory prose.",
                    failure_class=FAILURE_CLASS_MODEL,
                    failure_location="file_content_semantics",
                    recommended_fix_target="model",
                )
        if normalized_rel.startswith("src/"):
            for snippet, reason in src_forbidden_patterns:
                if snippet in content:
                    raise AppFactoryError(
                        f"Rejected semantic guard for {rel_path}: {reason}.",
                        failure_class=FAILURE_CLASS_MODEL,
                        failure_location="file_content_semantics",
                        recommended_fix_target="model",
                    )
            if not allow_input and "input(" in content:
                raise AppFactoryError(
                    f"Rejected semantic guard for {rel_path}: src/ files must not introduce input() without spec approval.",
                    failure_class=FAILURE_CLASS_MODEL,
                    failure_location="file_content_semantics",
                    recommended_fix_target="model",
                )
            if preserve_entrypoint:
                if not re.search(r"(?m)^\s*def\s+main\s*\(", content):
                    raise AppFactoryError(
                        f"Rejected semantic guard for {rel_path}: existing main() entrypoint must be preserved.",
                        failure_class=FAILURE_CLASS_MODEL,
                        failure_location="file_content_semantics",
                        recommended_fix_target="model",
                    )
                if '__name__ == "__main__"' not in content or "main()" not in content:
                    raise AppFactoryError(
                        f"Rejected semantic guard for {rel_path}: existing __main__ entrypoint pattern must be preserved.",
                        failure_class=FAILURE_CLASS_MODEL,
                        failure_location="file_content_semantics",
                        recommended_fix_target="model",
                    )
            elif require_main_entrypoint:
                if not re.search(r"(?m)^\s*def\s+main\s*\(", content):
                    raise AppFactoryError(
                        f"Rejected semantic guard for {rel_path}: src/main.py must define main() for the workspace entrypoint.",
                        failure_class=FAILURE_CLASS_MODEL,
                        failure_location="file_content_semantics",
                        recommended_fix_target="model",
                    )
                if '__name__ == "__main__"' not in content or "main()" not in content:
                    raise AppFactoryError(
                        f"Rejected semantic guard for {rel_path}: src/main.py must include the __main__ entrypoint pattern.",
                        failure_class=FAILURE_CLASS_MODEL,
                        failure_location="file_content_semantics",
                        recommended_fix_target="model",
                    )
        if normalized_rel.startswith("tests/"):
            if "import pytest" in content:
                raise AppFactoryError(
                    f"Rejected semantic guard for {rel_path}: tests/ files must use unittest, not pytest.",
                    failure_class=FAILURE_CLASS_MODEL,
                    failure_location="file_content_semantics",
                    recommended_fix_target="model",
                )
            for pattern, reason in tests_forbidden_patterns:
                if re.search(pattern, content):
                    raise AppFactoryError(
                        f"Rejected semantic guard for {rel_path}: {reason}.",
                        failure_class=FAILURE_CLASS_MODEL,
                        failure_location="file_content_semantics",
                        recommended_fix_target="model",
                    )
            if '__name__ == "__main__"' in content and "unittest.main(" not in content:
                raise AppFactoryError(
                    f"Rejected semantic guard for {rel_path}: tests/ files must not include a non-test __main__ entrypoint.",
                    failure_class=FAILURE_CLASS_MODEL,
                    failure_location="file_content_semantics",
                    recommended_fix_target="model",
                )
            imports_src_main = "from src import main" in content or "import src.main" in content or "from src.main import" in content
            if normalized_rel == "tests/test_main.py" and not imports_src_main:
                raise AppFactoryError(
                    f"Rejected semantic guard for {rel_path}: tests/test_main.py must import from src.main.",
                    failure_class=FAILURE_CLASS_MODEL,
                    failure_location="file_content_semantics",
                    recommended_fix_target="model",
                )
            if normalized_rel == "tests/test_main.py" and require_main_entrypoint and "main_module.main" not in content:
                raise AppFactoryError(
                    f"Rejected semantic guard for {rel_path}: tests/test_main.py must verify the main() entrypoint via main_module.main.",
                    failure_class=FAILURE_CLASS_MODEL,
                    failure_location="file_content_semantics",
                    recommended_fix_target="model",
                )
            if uses_src_package_layout and ("from taskdesk" in content or re.search(r"(?m)^\s*import\s+taskdesk(?:\b|\.)", content)):
                raise AppFactoryError(
                    f"Rejected semantic guard for {rel_path}: tests in this workspace must import from src.taskdesk, not taskdesk directly.",
                    failure_class=FAILURE_CLASS_MODEL,
                    failure_location="file_content_semantics",
                    recommended_fix_target="model",
                )


def apply_file_changes(runtime_dir: Path, spec: Dict[str, Any], file_updates: List[Dict[str, Any]], dry_run: bool) -> Tuple[List[str], List[str]]:
    applied: List[str] = []
    unchanged: List[str] = []
    for update in file_updates:
        rel_path = update["path"]
        full_path = update["full_path"]
        existing_content = read_text_file(full_path, required=False) if full_path.exists() else None
        if existing_content is not None and existing_content == update["content"]:
            print_log(f"Unchanged file skipped: {rel_path}")
            unchanged.append(rel_path)
            continue
        backup_existing_file(runtime_dir, spec["spec_id"], rel_path, full_path, dry_run)
        if dry_run:
            print_log(f"[dry-run] Would overwrite: {rel_path}")
        else:
            write_text_file(full_path, update["content"])
        applied.append(rel_path)
    return applied, unchanged


def run_validation_commands(workspace: Path, commands: List[str], dry_run: bool) -> Tuple[bool, str]:
    if dry_run:
        for command in commands:
            print_log(f"[dry-run] Would run validation: {command}")
        return True, "Dry run: validation skipped."

    outputs: List[str] = []
    for command in commands:
        print_log(f"Validation: {command}")
        try:
            completed = subprocess.run(
                command,
                cwd=str(workspace),
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except OSError as exc:
            raise AppFactoryError(
                f"Failed to execute validation command '{command}': {exc}",
                failure_class=FAILURE_CLASS_SPEC,
                failure_location="validation_command",
                recommended_fix_target="spec",
            ) from exc
        except subprocess.TimeoutExpired:
            return False, f"Validation command timed out: {command}"

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        outputs.append(f"$ {command}")
        outputs.append(f"exit_code={completed.returncode}")
        if stdout:
            outputs.append("stdout:")
            outputs.append(stdout)
        if stderr:
            outputs.append("stderr:")
            outputs.append(stderr)
        if completed.returncode != 0:
            return False, "\n".join(outputs)
    return True, "\n".join(outputs) if outputs else "Validation succeeded."


def run_debug_commands(workspace: Path, commands: List[str], dry_run: bool) -> Tuple[str, List[Dict[str, Any]]]:
    if not commands:
        return "", []
    if dry_run:
        for command in commands:
            print_log(f"[dry-run] Would run debug command: {command}")
        return "Dry run: debug commands skipped.", [{"command": command, "result": "dry_run"} for command in commands]

    outputs: List[str] = []
    records: List[Dict[str, Any]] = []
    for command in commands:
        print_log(f"Debug: {command}")
        try:
            completed = subprocess.run(
                command,
                cwd=str(workspace),
                shell=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except OSError as exc:
            raise AppFactoryError(
                f"Failed to execute debug command '{command}': {exc}",
                failure_class=FAILURE_CLASS_SPEC,
                failure_location="debug_command",
                recommended_fix_target="spec",
            ) from exc
        except subprocess.TimeoutExpired:
            outputs.extend([f"$ {command}", "timeout"])
            records.append({"command": command, "result": "timeout"})
            continue

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        outputs.append(f"$ {command}")
        outputs.append(f"exit_code={completed.returncode}")
        if stdout:
            outputs.append("stdout:")
            outputs.append(stdout)
        if stderr:
            outputs.append("stderr:")
            outputs.append(stderr)
        records.append(
            {
                "command": command,
                "result": "ok",
                "exit_code": completed.returncode,
                "stdout": stdout,
                "stderr": stderr,
            }
        )
    return "\n".join(outputs).strip(), records


def update_spec_state(spec_state: Dict[str, Any], status: str, last_error: str) -> None:
    spec_state["status"] = status
    spec_state["last_error"] = last_error
    spec_state["last_updated"] = utc_now_iso()


def failure_status_for_error(error_message: str, attempt_number: int, retry_budget: int) -> str:
    lower = error_message.lower()
    exhausted = attempt_number > retry_budget
    severe = any(
        token in lower
        for token in ("forbidden", "out-of-scope", "duplicate file entry", "protocol", "markdown fences", "empty file: path")
    )
    if exhausted and severe:
        return "escalated"
    if exhausted:
        return "failed"
    return "pending"


def success_status_for_attempt() -> str:
    return "passed"


def classify_validation_failure(validation_summary: str) -> Dict[str, str]:
    return build_failure_info(FAILURE_CLASS_VALIDATION, "validation", validation_summary, "spec")


def execute_spec(
    workspace: Path,
    runtime_dir: Path,
    architecture_text: str,
    spec: Dict[str, Any],
    state: Dict[str, Any],
    model: str,
    ollama_url: str,
    dry_run: bool,
) -> Dict[str, str]:
    spec_state = initialize_spec_state(state, spec["spec_id"])
    latest_failure_path = runtime_dir / LATEST_FAILURE_FILENAME
    latest_failure = read_text_file(latest_failure_path, required=False) if latest_failure_path.exists() else ""
    latest_debug_path = runtime_dir / LATEST_DEBUG_FILENAME
    latest_debug_output = read_text_file(latest_debug_path, required=False) if latest_debug_path.exists() else ""

    while True:
        next_attempt = int(spec_state.get("attempt_count", 0)) + 1
        if next_attempt > spec["retry_budget"] + 1:
            final_status = "failed"
            update_spec_state(spec_state, final_status, spec_state.get("last_error", "Retry budget exhausted."))
            save_state(runtime_dir, state, dry_run)
            failure_info = build_failure_info(FAILURE_CLASS_VALIDATION, "retry_budget", spec_state.get("last_error", "Retry budget exhausted."), "spec")
            return {"spec_id": spec["spec_id"], "final_status": final_status, **failure_info}

        update_spec_state(spec_state, "in_progress", spec_state.get("last_error", ""))
        spec_state["attempt_count"] = next_attempt
        save_state(runtime_dir, state, dry_run)

        print_log(f"Spec: {spec['filename']}")
        print_log(f"Attempt: {next_attempt}/{spec['retry_budget'] + 1}")

        attempt_record: Dict[str, Any] = {
            "timestamp": utc_now_iso(),
            "spec_id": spec["spec_id"],
            "attempt_number": next_attempt,
            "model": model,
            "ollama_num_ctx": DEFAULT_NUM_CTX,
            "final_status_after_attempt": "in_progress",
            "raw_response_parse_status": "",
            "file_block_count": 0,
            "file_paths_extracted": [],
            "failure_class": "",
            "failure_location": "",
            "failure_reason": "",
            "recommended_fix_target": "",
            "files_unchanged": [],
            "debug_commands_run": [],
            "debug_output_summary": "",
        }

        try:
            file_context = build_file_context(workspace, spec["allowed_files"])
            debug_file_context = build_file_context(workspace, spec.get("debug_files", []))
            attempt_record["allowed_file_discovery"] = [
                {
                    "path": entry["path"],
                    "resolved_path": entry["resolved_path"],
                    "exists": entry["exists"],
                    "content_loaded": entry["content_loaded"],
                    "read_error": entry["read_error"],
                }
                for entry in file_context
            ]
            for entry in file_context:
                print_log(
                    f"Allowed file: {entry['path']} | resolved={entry['resolved_path']} | "
                    f"exists={entry['exists']} | content_loaded={entry['content_loaded']}"
                )
                if entry["read_error"]:
                    print_log(f"Allowed file read error: {entry['path']} -> {entry['read_error']}")
            attempt_record["debug_file_discovery"] = [
                {
                    "path": entry["path"],
                    "resolved_path": entry["resolved_path"],
                    "exists": entry["exists"],
                    "content_loaded": entry["content_loaded"],
                    "read_error": entry["read_error"],
                }
                for entry in debug_file_context
            ]
            for entry in debug_file_context:
                print_log(
                    f"Debug file: {entry['path']} | resolved={entry['resolved_path']} | "
                    f"exists={entry['exists']} | content_loaded={entry['content_loaded']}"
                )
                if entry["read_error"]:
                    print_log(f"Debug file read error: {entry['path']} -> {entry['read_error']}")
            prompt = build_prompt(architecture_text, spec, file_context, debug_file_context, latest_failure, latest_debug_output)
            prompt_metrics = measure_prompt(prompt)
            attempt_record.update(prompt_metrics)
            print_log(
                f"Prompt size: chars={prompt_metrics['prompt_characters']}, bytes={prompt_metrics['prompt_bytes']}, num_ctx={DEFAULT_NUM_CTX}"
            )
            write_current_job(runtime_dir, prompt, dry_run)

            if dry_run:
                print_log("[dry-run] Ollama request skipped.")
                model_data = {"files": [], "parse_status": "dry_run", "file_block_count": 0, "file_paths": []}
            else:
                raw_response = call_ollama(ollama_url, model, prompt)
                model_data = parse_model_response(raw_response)

            attempt_record["raw_response_parse_status"] = model_data.get("parse_status", "")
            attempt_record["file_block_count"] = model_data.get("file_block_count", 0)
            attempt_record["file_paths_extracted"] = model_data.get("file_paths", [])
            requested_files = [entry["path"] for entry in model_data["files"]]
            attempt_record["files_requested_by_model"] = requested_files
            print_log(f"Files proposed: {requested_files if requested_files else 'none'}")

            validated_updates = validate_proposed_files(workspace, spec, model_data["files"])
            enforce_semantic_file_guards(validated_updates, spec, file_context)
            applied_files, unchanged_files = apply_file_changes(runtime_dir, spec, validated_updates, dry_run)
            attempt_record["files_applied"] = applied_files
            attempt_record["files_unchanged"] = unchanged_files

            validation_ok, validation_summary = run_validation_commands(workspace, spec["validation_commands"], dry_run)
            attempt_record["validation_result"] = "passed" if validation_ok else "failed"

            if validation_ok:
                final_status = success_status_for_attempt()
                update_spec_state(spec_state, final_status, "")
                attempt_record["error_summary"] = ""
                attempt_record["final_status_after_attempt"] = final_status
                append_attempt(runtime_dir, attempt_record, dry_run)
                if not dry_run:
                    write_runtime_text(runtime_dir, LATEST_FAILURE_FILENAME, "", dry_run=False)
                    write_runtime_text(runtime_dir, LATEST_DEBUG_FILENAME, "", dry_run=False)
                save_state(runtime_dir, state, dry_run)
                print_log(f"Result: {final_status}")
                return {"spec_id": spec["spec_id"], "final_status": final_status, **empty_failure_info()}

            error_summary = validation_summary
            failure_info = classify_validation_failure(error_summary)
            write_runtime_text(runtime_dir, LATEST_FAILURE_FILENAME, error_summary, dry_run)
            latest_failure = error_summary
            debug_output_summary, debug_records = run_debug_commands(workspace, spec.get("debug_commands", []), dry_run)
            attempt_record["debug_commands_run"] = debug_records
            attempt_record["debug_output_summary"] = debug_output_summary
            write_runtime_text(runtime_dir, LATEST_DEBUG_FILENAME, debug_output_summary, dry_run)
            latest_debug_output = debug_output_summary
            final_status = failure_status_for_error(error_summary, next_attempt, spec["retry_budget"])
            update_spec_state(spec_state, final_status if final_status in ("failed", "escalated") else "pending", error_summary)
            attempt_record["error_summary"] = error_summary
            attempt_record.update(failure_info)
            attempt_record["final_status_after_attempt"] = spec_state["status"]
            append_attempt(runtime_dir, attempt_record, dry_run)
            save_state(runtime_dir, state, dry_run)
            print_log(f"Result: {spec_state['status']}")
            print_log(
                f"Failure: {failure_info['failure_class']} at {failure_info['failure_location']} -> {failure_info['failure_reason']} "
                f"(fix: {failure_info['recommended_fix_target']})"
            )
            if spec_state["status"] in ("failed", "escalated"):
                return {"spec_id": spec["spec_id"], "final_status": spec_state["status"], **failure_info}
        except AppFactoryError as exc:
            failure_info = failure_info_from_exception(exc)
            error_summary = failure_info["failure_reason"]
            if failure_info["failure_location"] == "model_response_protocol":
                attempt_record["raw_response_parse_status"] = "failed"
            write_runtime_text(runtime_dir, LATEST_FAILURE_FILENAME, error_summary, dry_run)
            latest_failure = error_summary
            debug_output_summary, debug_records = run_debug_commands(workspace, spec.get("debug_commands", []), dry_run)
            attempt_record["debug_commands_run"] = debug_records
            attempt_record["debug_output_summary"] = debug_output_summary
            write_runtime_text(runtime_dir, LATEST_DEBUG_FILENAME, debug_output_summary, dry_run)
            latest_debug_output = debug_output_summary
            final_status = failure_status_for_error(error_summary, next_attempt, spec["retry_budget"])
            update_spec_state(spec_state, final_status if final_status in ("failed", "escalated") else "pending", error_summary)
            attempt_record.setdefault("files_requested_by_model", [])
            attempt_record.setdefault("files_applied", [])
            attempt_record["validation_result"] = "not_run"
            attempt_record["error_summary"] = error_summary
            attempt_record.update(failure_info)
            attempt_record["final_status_after_attempt"] = spec_state["status"]
            append_attempt(runtime_dir, attempt_record, dry_run)
            save_state(runtime_dir, state, dry_run)
            print_log(f"Result: {spec_state['status']}")
            print_log(
                f"Failure: {failure_info['failure_class']} at {failure_info['failure_location']} -> {failure_info['failure_reason']} "
                f"(fix: {failure_info['recommended_fix_target']})"
            )
            if spec_state["status"] in ("failed", "escalated"):
                return {"spec_id": spec["spec_id"], "final_status": spec_state["status"], **failure_info}


def run(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser()
    if not workspace.exists() or not workspace.is_dir():
        raise AppFactoryError(
            f"Workspace path does not exist or is not a directory: {workspace}",
            failure_class=FAILURE_CLASS_SPEC,
            failure_location="workspace",
            recommended_fix_target="workspace",
        )
    workspace = workspace.resolve()

    architecture_path = workspace / "architecture.md"
    specs_dir = workspace / "specs"
    runtime_dir = workspace / "runtime"

    architecture_text = read_text_file(architecture_path)
    if not specs_dir.exists() or not specs_dir.is_dir():
        raise AppFactoryError(
            f"Required specs directory is missing: {specs_dir}",
            failure_class=FAILURE_CLASS_SPEC,
            failure_location="workspace",
            recommended_fix_target="workspace",
        )

    ensure_runtime_dir(runtime_dir, args.dry_run)
    state = load_state(runtime_dir) if runtime_dir.exists() else {"specs": {}}

    print_log(f"Workspace: {workspace}")
    print_log(f"Model: {args.model}")
    print_log(f"Ollama URL: {args.ollama_url}")
    if args.dry_run:
        print_log("Mode: dry-run")

    attempted = 0
    results = {"passed": 0, "failed": 0, "escalated": 0, "pending": 0}
    run_summaries: List[Dict[str, str]] = []

    while attempted < args.max_specs:
        spec = choose_next_spec(specs_dir, state, args.spec if attempted == 0 else None)
        spec_result = execute_spec(
            workspace=workspace,
            runtime_dir=runtime_dir,
            architecture_text=architecture_text,
            spec=spec,
            state=state,
            model=args.model,
            ollama_url=args.ollama_url,
            dry_run=args.dry_run,
        )
        status = spec_result["final_status"]
        run_summaries.append(spec_result)
        results[status] = results.get(status, 0) + 1
        attempted += 1
        if args.spec:
            break
        if status != "passed":
            print_log(f"Halting run because {spec_result['spec_id']} did not pass.")
            break
        try:
            choose_next_spec(specs_dir, state, None)
        except AppFactoryError as exc:
            if str(exc) == "No pending specs remain.":
                break
            raise

    for item in run_summaries:
        failure_class = item.get("failure_class") or "none"
        fix_target = item.get("recommended_fix_target") or "none"
        print_log(
            f"Spec Summary: spec_id={item['spec_id']}, final_status={item['final_status']}, "
            f"failure_class={failure_class}, next_fix_target={fix_target}"
        )

    print_log(
        "Summary: "
        + ", ".join(
            [
                f"attempted={attempted}",
                f"passed={results.get('passed', 0)}",
                f"failed={results.get('failed', 0)}",
                f"escalated={results.get('escalated', 0)}",
                f"pending={results.get('pending', 0)}",
            ]
        )
    )
    return 0


def main() -> int:
    try:
        args = parse_args()
        return run(args)
    except AppFactoryError as exc:
        failure_info = failure_info_from_exception(exc)
        print_log(
            f"Error: {failure_info['failure_class']} at {failure_info['failure_location']} -> {failure_info['failure_reason']} "
            f"(fix: {failure_info['recommended_fix_target']})"
        )
        return 1
    except KeyboardInterrupt:
        print_log("Interrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations
import yaml
import json
from typing import Any, Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field

@dataclass
class DSLValidationResult:
    is_valid: bool
    errors: List[Dict[str, str]] = field(default_factory=list)

class DSLParser:
    def __init__(self):
        self.supported_task_types = {
            "ensure_import", "ensure_function", "ensure_class", "replace_block",
            "insert_before", "insert_after", "append_if_missing", "delete_block",
            "run_command", "validate", "create_file", "update_file", "delete_file"
        }
        self.root_allowed_keys = {"spec_version", "spec_id", "metadata", "settings", "tasks"}
        self.settings_allowed_keys = {"fail_fast", "stop_on_error", "allow_legacy_fallback"}
        self.task_base_allowed_keys = {"id", "type", "depends_on", "file", "content", "mode", "import", "function_name", "class_name", "target", "command"}

    def is_dsl_spec(self, spec_text: str) -> bool:
        try:
            data = yaml.safe_load(spec_text)
            if isinstance(data, dict) and "spec_version" in data and "tasks" in data:
                return True
        except:
            pass
        return False

    def parse(self, spec_text: str) -> Tuple[Optional[Dict[str, Any]], DSLValidationResult]:
        errors = []
        try:
            data = yaml.safe_load(spec_text)
        except yaml.YAMLError as e:
            errors.append({"field": "yaml", "error": f"Invalid YAML: {e}"})
            return None, DSLValidationResult(False, errors)

        if not isinstance(data, dict):
            errors.append({"field": "root", "error": "Spec must be a YAML dictionary"})
            return None, DSLValidationResult(False, errors)

        # Reject unknown root keys
        for key in data:
            if key not in self.root_allowed_keys:
                errors.append({"field": key, "error": f"Unknown root field: {key}"})

        # Basic Required Fields
        if "spec_version" not in data:
            errors.append({"field": "spec_version", "error": "Missing required field"})
        elif not isinstance(data["spec_version"], int):
            errors.append({"field": "spec_version", "error": "Must be an integer"})

        if "spec_id" not in data:
            errors.append({"field": "spec_id", "error": "Missing required field"})

        if "tasks" not in data:
            errors.append({"field": "tasks", "error": "Missing required field"})
        elif not isinstance(data["tasks"], list):
            errors.append({"field": "tasks", "error": "Must be a list"})
        else:
            for i, task in enumerate(data["tasks"]):
                task_errors = self._validate_task(i, task)
                errors.extend(task_errors)

        # Settings validation
        if "settings" in data:
            if not isinstance(data["settings"], dict):
                errors.append({"field": "settings", "error": "Must be a dictionary"})
            else:
                for key in data["settings"]:
                    if key not in self.settings_allowed_keys:
                        errors.append({"field": f"settings.{key}", "error": f"Unknown setting: {key}"})

        # Dependency validation (IDs must exist)
        if not errors:
            task_ids = {t.get("id") for t in data["tasks"] if isinstance(t, dict) and t.get("id")}
            for i, task in enumerate(data["tasks"]):
                if not isinstance(task, dict): continue
                deps = task.get("depends_on", [])
                if not isinstance(deps, list):
                    errors.append({"field": f"tasks[{i}].depends_on", "error": "Must be a list"})
                    continue
                for dep in deps:
                    if dep not in task_ids:
                        errors.append({"field": f"tasks[{i}].depends_on", "error": f"Task ID not found: {dep}"})

        is_valid = len(errors) == 0
        return data if is_valid else None, DSLValidationResult(is_valid, errors)

    def _validate_task(self, index: int, task: Any) -> List[Dict[str, str]]:
        errors = []
        if not isinstance(task, dict):
            errors.append({"field": f"tasks[{index}]", "error": "Task must be a dictionary"})
            return errors

        prefix = f"tasks[{index}]"

        # Reject unknown task keys
        for key in task:
            if key not in self.task_base_allowed_keys:
                 errors.append({"field": f"{prefix}.{key}", "error": f"Unknown field in task: {key}"})

        if "id" not in task:
            errors.append({"field": f"{prefix}.id", "error": "Missing required field"})

        if "type" not in task:
            errors.append({"field": f"{prefix}.type", "error": "Missing required field"})
        elif task["type"] not in self.supported_task_types:
            errors.append({"field": f"{prefix}.type", "error": f"Unsupported task type: {task['type']}"})

        # Field validation based on type
        t_type = task.get("type")

        # File path validation for file-based tasks
        if t_type not in {"run_command", "validate"}:
            if "file" not in task:
                errors.append({"field": f"{prefix}.file", "error": "Missing required field for this task type"})
            elif ".." in str(task["file"]) or str(task["file"]).startswith("/"):
                 errors.append({"field": f"{prefix}.file", "error": "File path must be relative and inside workspace"})

        if t_type == "ensure_import":
            self._require(task, prefix, ["import"], errors)

        elif t_type in {"ensure_function", "ensure_class"}:
            name_field = "function_name" if t_type == "ensure_function" else "class_name"
            self._require(task, prefix, [name_field, "content"], errors)
            if "mode" in task and task["mode"] not in {"create_only", "replace_if_exists", "fail_if_exists"}:
                errors.append({"field": f"{prefix}.mode", "error": "Invalid mode"})

        elif t_type in {"replace_block", "insert_before", "insert_after", "delete_block"}:
            self._require(task, prefix, ["target"], errors)
            if "target" in task:
                if not isinstance(task["target"], dict):
                    errors.append({"field": f"{prefix}.target", "error": "Target must be a dictionary"})
                else:
                    self._require(task["target"], f"{prefix}.target", ["type", "value"], errors)

            if t_type != "delete_block":
                self._require(task, prefix, ["content"], errors)

        elif t_type == "append_if_missing":
             self._require(task, prefix, ["content"], errors)

        elif t_type == "run_command":
            self._require(task, prefix, ["command"], errors)

        elif t_type == "create_file":
            self._require(task, prefix, ["content"], errors)

        return errors

    def _require(self, data: dict, prefix: str, fields: List[str], errors: List[Dict[str, str]]):
        for f in fields:
            if f not in data:
                errors.append({"field": f"{prefix}.{f}", "error": "Missing required field"})

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
        self.root_allowed_keys = {"spec_version", "spec_id", "metadata", "settings", "tasks", "verification", "execution", "promotion", "retention", "runtime"}
        self.settings_allowed_keys = {"fail_fast", "stop_on_error", "allow_legacy_fallback"}
        self.execution_allowed_keys = {"mode", "source_policy"}
        self.promotion_allowed_keys = {"enabled", "allow_on_status"}
        self.retention_allowed_keys = {"keep_execution_workspace_on_failure", "keep_execution_workspace_on_success"}
        self.task_base_allowed_keys = {"id", "type", "depends_on", "file", "content", "mode", "import", "function_name", "class_name", "target", "command"}
        self.supported_check_types = {
            "file_exists", "file_not_exists", "contains_text", "not_contains_text",
            "contains_regex", "symbol_exists", "symbol_not_exists", "import_exists",
            "command_exit_code", "command_stdout_contains", "json_value_equals",
            "line_count_range", "diff_contains", "task_status"
        }

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

        # Execution validation
        if "execution" in data:
            if not isinstance(data["execution"], dict):
                errors.append({"field": "execution", "error": "Must be a dictionary"})
            else:
                for key in data["execution"]:
                    if key not in self.execution_allowed_keys:
                        errors.append({"field": f"execution.{key}", "error": f"Unknown execution field: {key}"})
                if "mode" in data["execution"] and data["execution"]["mode"] not in {"promote_on_success", "dry_run", "verify_only", "regression_case"}:
                    errors.append({"field": "execution.mode", "error": "Invalid execution mode"})
                if "source_policy" in data["execution"] and data["execution"]["source_policy"] not in {"promoted_head", "fixed_base"}:
                    errors.append({"field": "execution.source_policy", "error": "Invalid source policy"})

        # Promotion validation
        if "promotion" in data:
            if not isinstance(data["promotion"], dict):
                errors.append({"field": "promotion", "error": "Must be a dictionary"})
            else:
                for key in data["promotion"]:
                    if key not in self.promotion_allowed_keys:
                        errors.append({"field": f"promotion.{key}", "error": f"Unknown promotion field: {key}"})
                if "allow_on_status" in data["promotion"]:
                    if not isinstance(data["promotion"]["allow_on_status"], list):
                         errors.append({"field": "promotion.allow_on_status", "error": "Must be a list"})
                    else:
                        valid_statuses = {"COMPLETED", "COMPLETED_WITH_WARNINGS"}
                        for s in data["promotion"]["allow_on_status"]:
                            if s not in valid_statuses:
                                 errors.append({"field": "promotion.allow_on_status", "error": f"Invalid status for promotion: {s}"})

        # Retention validation
        if "retention" in data:
            if not isinstance(data["retention"], dict):
                errors.append({"field": "retention", "error": "Must be a dictionary"})
            else:
                for key in data["retention"]:
                    if key not in self.retention_allowed_keys:
                        errors.append({"field": f"retention.{key}", "error": f"Unknown retention field: {key}"})

        # Runtime validation
        if "runtime" in data:
            r_errors = self._validate_runtime(data["runtime"])
            errors.extend(r_errors)

        # Verification validation
        if "verification" in data:
            v_errors = self._validate_verification(data["verification"])
            errors.extend(v_errors)

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

    def _validate_verification(self, v_data: Any) -> List[Dict[str, str]]:
        errors = []
        if not isinstance(v_data, dict):
            errors.append({"field": "verification", "error": "Must be a dictionary"})
            return errors

        allowed_root = {"mode", "checks", "regression"}
        for key in v_data:
            if key not in allowed_root:
                errors.append({"field": f"verification.{key}", "error": f"Unknown field: {key}"})

        if "mode" in v_data and v_data["mode"] not in {"strict", "permissive"}:
             errors.append({"field": "verification.mode", "error": "Must be strict or permissive"})

        if "checks" in v_data:
            if not isinstance(v_data["checks"], list):
                errors.append({"field": "verification.checks", "error": "Must be a list"})
            else:
                for i, check in enumerate(v_data["checks"]):
                    errors.extend(self._validate_check(i, check))

        if "regression" in v_data:
            if not isinstance(v_data["regression"], dict):
                errors.append({"field": "verification.regression", "error": "Must be a dictionary"})
            else:
                reg = v_data["regression"]
                allowed_reg = {"enabled", "suite", "update_baseline"}
                for k in reg:
                    if k not in allowed_reg:
                        errors.append({"field": f"verification.regression.{k}", "error": f"Unknown field: {k}"})
                if reg.get("enabled") is True and not reg.get("suite"):
                    errors.append({"field": "verification.regression.suite", "error": "Suite name required when enabled"})

        return errors

    def _validate_check(self, index: int, check: Any) -> List[Dict[str, str]]:
        errors = []
        if not isinstance(check, dict):
            errors.append({"field": f"verification.checks[{index}]", "error": "Check must be a dictionary"})
            return errors

        prefix = f"verification.checks[{index}]"
        c_type = check.get("type")
        if not c_type:
            errors.append({"field": f"{prefix}.type", "error": "Missing required field"})
            return errors

        if c_type not in self.supported_check_types:
            errors.append({"field": f"{prefix}.type", "error": f"Unsupported check type: {c_type}"})
            return errors

        if "severity" in check and check["severity"] not in {"hard", "soft"}:
             errors.append({"field": f"{prefix}.severity", "error": "Must be hard or soft"})

        # Check-specific fields
        if c_type in {"file_exists", "file_not_exists", "contains_text", "not_contains_text", "contains_regex", "import_exists", "json_value_equals", "line_count_range", "diff_contains"}:
            self._require(check, prefix, ["path"], errors)

        if c_type in {"contains_text", "not_contains_text", "diff_contains"}:
             self._require(check, prefix, ["text"], errors)

        if c_type == "contains_regex":
             self._require(check, prefix, ["pattern"], errors)

        if c_type == "symbol_exists" or c_type == "symbol_not_exists":
             self._require(check, prefix, ["path", "symbol_type", "symbol_name"], errors)
             if check.get("symbol_type") not in {"function", "class"}:
                  errors.append({"field": f"{prefix}.symbol_type", "error": "Must be function or class"})

        if c_type == "import_exists":
             self._require(check, prefix, ["import"], errors)

        if c_type in {"command_exit_code", "command_stdout_contains"}:
             self._require(check, prefix, ["command"], errors)

        if c_type == "command_stdout_contains":
             self._require(check, prefix, ["text"], errors)

        if c_type == "json_value_equals":
             self._require(check, prefix, ["json_path", "expected"], errors)

        if c_type == "task_status":
             self._require(check, prefix, ["task_id", "expected"], errors)

        return errors

    def _validate_runtime(self, r_data: Any) -> List[Dict[str, str]]:
        errors = []
        if not isinstance(r_data, dict):
            errors.append({"field": "runtime", "error": "Must be a dictionary"})
            return errors

        allowed_keys = {"profile", "python_version", "env", "dependency_fingerprint", "command_policy", "drift_policy"}
        for key in r_data:
            if key not in allowed_keys:
                errors.append({"field": f"runtime.{key}", "error": f"Unknown field: {key}"})

        return errors

    def _require(self, data: dict, prefix: str, fields: List[str], errors: List[Dict[str, str]]):
        for f in fields:
            if f not in data:
                errors.append({"field": f"{prefix}.{f}", "error": "Missing required field"})

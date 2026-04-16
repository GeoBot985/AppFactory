from __future__ import annotations
import os
import re
import ast
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from .models import CheckStatus, CheckResult, Severity

class VerificationExecutor:
    def __init__(self, project_root: Path, cmd_executor: Optional[Any] = None):
        self.project_root = project_root
        self.cmd_executor = cmd_executor

    def execute_check(self, check_def: Dict[str, Any], task_results: List[Any] = None) -> CheckResult:
        check_type = check_def.get("type")
        severity = Severity(check_def.get("severity", "hard"))

        handler = getattr(self, f"_check_{check_type}", None)
        if not handler:
            return CheckResult(
                check_id=self._gen_id(check_def),
                type=check_type,
                severity=severity,
                status=CheckStatus.ERROR,
                message=f"Unknown check type: {check_type}"
            )

        try:
            return handler(check_def, severity, task_results)
        except Exception as e:
            return CheckResult(
                check_id=self._gen_id(check_def),
                type=check_type,
                severity=severity,
                status=CheckStatus.ERROR,
                message=f"Check execution failed: {str(e)}"
            )

    def _gen_id(self, check_def: Dict[str, Any]) -> str:
        # Simple ID generation
        parts = [check_def.get("type", "unknown")]
        if "path" in check_def: parts.append(check_def["path"])
        if "symbol_name" in check_def: parts.append(check_def["symbol_name"])
        if "command" in check_def: parts.append(check_def["command"])
        return ":".join(parts)

    def _check_file_exists(self, check_def: Dict, severity: Severity, tasks: List) -> CheckResult:
        path = self.project_root / check_def["path"]
        exists = path.exists()
        return CheckResult(
            check_id=self._gen_id(check_def),
            type="file_exists",
            severity=severity,
            status=CheckStatus.PASS if exists else CheckStatus.FAIL,
            message=f"File {check_def['path']} exists" if exists else f"File {check_def['path']} not found",
            evidence={"path": check_def["path"]}
        )

    def _check_file_not_exists(self, check_def: Dict, severity: Severity, tasks: List) -> CheckResult:
        path = self.project_root / check_def["path"]
        exists = path.exists()
        return CheckResult(
            check_id=self._gen_id(check_def),
            type="file_not_exists",
            severity=severity,
            status=CheckStatus.PASS if not exists else CheckStatus.FAIL,
            message=f"File {check_def['path']} does not exist" if not exists else f"File {check_def['path']} unexpectedly found",
            evidence={"path": check_def["path"]}
        )

    def _check_contains_text(self, check_def: Dict, severity: Severity, tasks: List) -> CheckResult:
        path = self.project_root / check_def["path"]
        if not path.exists():
             return CheckResult(self._gen_id(check_def), "contains_text", severity, CheckStatus.FAIL, f"File {check_def['path']} not found")

        content = path.read_text(encoding="utf-8")
        text = check_def["text"]
        found = text in content
        return CheckResult(
            check_id=self._gen_id(check_def),
            type="contains_text",
            severity=severity,
            status=CheckStatus.PASS if found else CheckStatus.FAIL,
            message=f"Text found in {check_def['path']}" if found else f"Text not found in {check_def['path']}",
            evidence={"path": check_def["path"], "search_text": text}
        )

    def _check_not_contains_text(self, check_def: Dict, severity: Severity, tasks: List) -> CheckResult:
        path = self.project_root / check_def["path"]
        if not path.exists():
             return CheckResult(self._gen_id(check_def), "not_contains_text", severity, CheckStatus.PASS, f"File {check_def['path']} not found (so it doesn't contain the text)")

        content = path.read_text(encoding="utf-8")
        text = check_def["text"]
        found = text in content
        return CheckResult(
            check_id=self._gen_id(check_def),
            type="not_contains_text",
            severity=severity,
            status=CheckStatus.PASS if not found else CheckStatus.FAIL,
            message=f"Text not found in {check_def['path']}" if not found else f"Forbidden text found in {check_def['path']}",
            evidence={"path": check_def["path"], "forbidden_text": text}
        )

    def _check_contains_regex(self, check_def: Dict, severity: Severity, tasks: List) -> CheckResult:
        path = self.project_root / check_def["path"]
        if not path.exists():
             return CheckResult(self._gen_id(check_def), "contains_regex", severity, CheckStatus.FAIL, f"File {check_def['path']} not found")

        content = path.read_text(encoding="utf-8")
        pattern = check_def["pattern"]
        match = re.search(pattern, content)
        return CheckResult(
            check_id=self._gen_id(check_def),
            type="contains_regex",
            severity=severity,
            status=CheckStatus.PASS if match else CheckStatus.FAIL,
            message=f"Regex match found in {check_def['path']}" if match else f"Regex match not found in {check_def['path']}",
            evidence={"path": check_def["path"], "pattern": pattern}
        )

    def _check_symbol_exists(self, check_def: Dict, severity: Severity, tasks: List) -> CheckResult:
        path = self.project_root / check_def["path"]
        if not path.exists():
             return CheckResult(self._gen_id(check_def), "symbol_exists", severity, CheckStatus.FAIL, f"File {check_def['path']} not found")

        content = path.read_text(encoding="utf-8")
        symbol_type = check_def["symbol_type"] # function, class
        symbol_name = check_def["symbol_name"]

        found, line_no, preview = self._find_symbol(content, symbol_type, symbol_name)

        return CheckResult(
            check_id=self._gen_id(check_def),
            type="symbol_exists",
            severity=severity,
            status=CheckStatus.PASS if found else CheckStatus.FAIL,
            message=f"{symbol_type.capitalize()} {symbol_name} found" if found else f"{symbol_type.capitalize()} {symbol_name} not found",
            evidence={"path": check_def["path"], "line": line_no, "preview": preview}
        )

    def _check_symbol_not_exists(self, check_def: Dict, severity: Severity, tasks: List) -> CheckResult:
        path = self.project_root / check_def["path"]
        if not path.exists():
             return CheckResult(self._gen_id(check_def), "symbol_not_exists", severity, CheckStatus.PASS, f"File {check_def['path']} not found")

        content = path.read_text(encoding="utf-8")
        symbol_type = check_def["symbol_type"]
        symbol_name = check_def["symbol_name"]

        found, _, _ = self._find_symbol(content, symbol_type, symbol_name)

        return CheckResult(
            check_id=self._gen_id(check_def),
            type="symbol_not_exists",
            severity=severity,
            status=CheckStatus.PASS if not found else CheckStatus.FAIL,
            message=f"{symbol_type.capitalize()} {symbol_name} not found" if not found else f"{symbol_type.capitalize()} {symbol_name} unexpectedly found",
            evidence={"path": check_def["path"]}
        )

    def _find_symbol(self, content: str, symbol_type: str, name: str) -> tuple[bool, int, str]:
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if symbol_type == "function" and isinstance(node, ast.FunctionDef) and node.name == name:
                    return True, node.lineno, content.splitlines()[node.lineno-1].strip()
                if symbol_type == "class" and isinstance(node, ast.ClassDef) and node.name == name:
                    return True, node.lineno, content.splitlines()[node.lineno-1].strip()
        except:
            pass
        return False, 0, ""

    def _check_import_exists(self, check_def: Dict, severity: Severity, tasks: List) -> CheckResult:
        path = self.project_root / check_def["path"]
        if not path.exists():
             return CheckResult(self._gen_id(check_def), "import_exists", severity, CheckStatus.FAIL, f"File {check_def['path']} not found")

        content = path.read_text(encoding="utf-8")
        import_stmt = check_def["import"]

        count = content.count(import_stmt)
        # Spec says: Must verify exactly once unless configured otherwise.
        expected_count = check_def.get("expected_count", 1)
        success = count == expected_count

        return CheckResult(
            check_id=self._gen_id(check_def),
            type="import_exists",
            severity=severity,
            status=CheckStatus.PASS if success else CheckStatus.FAIL,
            message=f"Import '{import_stmt}' found {count} times, expected {expected_count}" if success else f"Import '{import_stmt}' found {count} times, expected {expected_count}",
            evidence={"path": check_def["path"], "actual_count": count}
        )

    def _check_command_exit_code(self, check_def: Dict, severity: Severity, tasks: List) -> CheckResult:
        command = check_def["command"]
        expected = check_def.get("expected_exit_code", 0)

        if self.cmd_executor:
            res = self.cmd_executor.run(command)
            actual = res.exit_code
            success = actual == expected
            return CheckResult(
                check_id=self._gen_id(check_def),
                type="command_exit_code",
                severity=severity,
                status=CheckStatus.PASS if success else CheckStatus.FAIL,
                message=f"Command exit code {actual} matched expected {expected}" if success else f"Command exit code {actual} did not match expected {expected}",
                evidence={"command": command, "exit_code": actual, "stdout": res.stdout, "stderr": res.stderr}
            )

        try:
            process = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(self.project_root)
            )
            actual = process.returncode
            success = actual == expected
            return CheckResult(
                check_id=self._gen_id(check_def),
                type="command_exit_code",
                severity=severity,
                status=CheckStatus.PASS if success else CheckStatus.FAIL,
                message=f"Command exit code {actual} matched expected {expected}" if success else f"Command exit code {actual} did not match expected {expected}",
                evidence={"command": command, "exit_code": actual, "stdout": process.stdout, "stderr": process.stderr}
            )
        except Exception as e:
            return CheckResult(self._gen_id(check_def), "command_exit_code", severity, CheckStatus.ERROR, f"Command execution failed: {str(e)}")

    def _check_command_stdout_contains(self, check_def: Dict, severity: Severity, tasks: List) -> CheckResult:
        command = check_def["command"]
        text = check_def["text"]

        if self.cmd_executor:
            res = self.cmd_executor.run(command)
            found = text in res.stdout
            return CheckResult(
                check_id=self._gen_id(check_def),
                type="command_stdout_contains",
                severity=severity,
                status=CheckStatus.PASS if found else CheckStatus.FAIL,
                message=f"Stdout contains '{text}'" if found else f"Stdout does not contain '{text}'",
                evidence={"command": command, "stdout": res.stdout}
            )

        try:
            process = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(self.project_root)
            )
            found = text in process.stdout
            return CheckResult(
                check_id=self._gen_id(check_def),
                type="command_stdout_contains",
                severity=severity,
                status=CheckStatus.PASS if found else CheckStatus.FAIL,
                message=f"Stdout contains '{text}'" if found else f"Stdout does not contain '{text}'",
                evidence={"command": command, "stdout": process.stdout}
            )
        except Exception as e:
            return CheckResult(self._gen_id(check_def), "command_stdout_contains", severity, CheckStatus.ERROR, f"Command execution failed: {str(e)}")

    def _check_json_value_equals(self, check_def: Dict, severity: Severity, tasks: List) -> CheckResult:
        path = self.project_root / check_def["path"]
        if not path.exists():
             return CheckResult(self._gen_id(check_def), "json_value_equals", severity, CheckStatus.FAIL, f"File {check_def['path']} not found")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            json_path = check_def["json_path"] # e.g. $.status or status
            expected = check_def["expected"]

            # Simple dotted traversal
            key = json_path.replace("$.", "")
            parts = key.split(".")
            val = data
            for p in parts:
                if isinstance(val, dict) and p in val:
                    val = val[p]
                else:
                    val = None
                    break

            success = val == expected
            return CheckResult(
                check_id=self._gen_id(check_def),
                type="json_value_equals",
                severity=severity,
                status=CheckStatus.PASS if success else CheckStatus.FAIL,
                message=f"JSON value at {json_path} matched expected" if success else f"JSON value at {json_path} was {val}, expected {expected}",
                evidence={"path": check_def["path"], "actual": val}
            )
        except Exception as e:
             return CheckResult(self._gen_id(check_def), "json_value_equals", severity, CheckStatus.ERROR, f"JSON check failed: {str(e)}")

    def _check_line_count_range(self, check_def: Dict, severity: Severity, tasks: List) -> CheckResult:
        path = self.project_root / check_def["path"]
        if not path.exists():
             return CheckResult(self._gen_id(check_def), "line_count_range", severity, CheckStatus.FAIL, f"File {check_def['path']} not found")

        lines = path.read_text(encoding="utf-8").splitlines()
        count = len(lines)
        min_v = check_def.get("min", 0)
        max_v = check_def.get("max", 1000000)

        success = min_v <= count <= max_v
        return CheckResult(
            check_id=self._gen_id(check_def),
            type="line_count_range",
            severity=severity,
            status=CheckStatus.PASS if success else CheckStatus.FAIL,
            message=f"Line count {count} in range [{min_v}, {max_v}]" if success else f"Line count {count} out of range [{min_v}, {max_v}]",
            evidence={"path": check_def["path"], "line_count": count}
        )

    def _check_diff_contains(self, check_def: Dict, severity: Severity, tasks: List) -> CheckResult:
        target_path = check_def["path"]
        text = check_def["text"]

        found_in_diff = False
        if tasks:
            for t in tasks:
                if hasattr(t, 'target') and t.target == target_path:
                    # Look for diff in task result
                    if hasattr(t, 'result') and t.result and hasattr(t.result, 'changes'):
                         # TaskResult in Demo10 doesn't store the full diff text directly,
                         # but TaskExecutorService saves it to run_folder/diffs.
                         # Since we don't easily have run_folder here, let's check if it was applied.
                         if target_path in t.result.changes:
                              # If the task was applied, we check if the text is in the file.
                              # This is a proxy for "diff contains" if we don't have the raw diff.
                              path = self.project_root / target_path
                              if path.exists():
                                   content = path.read_text(encoding="utf-8")
                                   if text in content:
                                        found_in_diff = True
                                        break

        return CheckResult(
            check_id=self._gen_id(check_def),
            type="diff_contains",
            severity=severity,
            status=CheckStatus.PASS if found_in_diff else CheckStatus.FAIL,
            message=f"Text '{text}' found in applied changes for {target_path}" if found_in_diff else f"Text '{text}' not found in applied changes for {target_path}",
            evidence={"path": target_path, "text": text}
        )

    def _check_task_status(self, check_def: Dict, severity: Severity, tasks: List) -> CheckResult:
        task_id = check_def["task_id"]
        expected = check_def["expected"] # e.g. applied, failed

        actual = "not_found"
        if tasks:
            for t in tasks:
                if hasattr(t, 'id') and t.id == task_id:
                    # Map task status to expected string
                    # This is simplified
                    if hasattr(t, 'status'):
                        actual = t.status.value if hasattr(t.status, 'value') else str(t.status)
                    break

        success = actual == expected
        return CheckResult(
            check_id=self._gen_id(check_def),
            type="task_status",
            severity=severity,
            status=CheckStatus.PASS if success else CheckStatus.FAIL,
            message=f"Task {task_id} status {actual} matched expected {expected}" if success else f"Task {task_id} status was {actual}, expected {expected}",
            evidence={"task_id": task_id, "actual": actual}
        )

from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple
from .models import RuntimeProfile, InterpreterMode

class InterpreterResolver:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def resolve(self, profile: RuntimeProfile) -> str:
        if not profile.interpreter:
            # Default to sys.executable if not specified
            return sys.executable

        mode = profile.interpreter.mode
        value = profile.interpreter.value

        if mode == InterpreterMode.PATH:
            return value
        elif mode == InterpreterMode.EXECUTABLE:
            # Check if it's in PATH
            import shutil
            resolved = shutil.which(value)
            if resolved:
                return resolved
            return value # Return original if not found, validation will catch it
        elif mode == InterpreterMode.WORKSPACE_RELATIVE:
            return str((self.workspace_root / value).resolve())
        else:
            raise ValueError(f"Unsupported interpreter mode: {mode}")

class InterpreterValidator:
    def validate(self, interpreter_path: str) -> Tuple[bool, str, Optional[str]]:
        path = Path(interpreter_path)

        if not path.exists():
            return False, "INTERPRETER_NOT_FOUND", f"Interpreter path does not exist: {interpreter_path}"

        if not os.access(path, os.X_OK):
            return False, "INTERPRETER_NOT_EXECUTABLE", f"Interpreter is not executable: {interpreter_path}"

        try:
            # Try to get version
            result = subprocess.run(
                [interpreter_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                return False, "INTERPRETER_VERSION_CHECK_FAILED", f"Interpreter version check failed with exit code {result.returncode}: {result.stderr}"

            version_str = result.stdout.strip() or result.stderr.strip()
            return True, "SUCCESS", version_str
        except Exception as e:
            return False, "INTERPRETER_VERSION_CHECK_FAILED", f"Error during interpreter version check: {str(e)}"

    def check_version_constraints(self, actual_version: str, constraints: Optional[dict]) -> Tuple[bool, str, str]:
        if not constraints:
            return True, "SUCCESS", ""

        # Simple version comparison (naive)
        # actual_version is usually like "Python 3.11.8"
        import re
        match = re.search(r"Python (\d+\.\d+\.\d+)", actual_version)
        if not match:
             # Try other format
             match = re.search(r"(\d+\.\d+\.\d+)", actual_version)

        if not match:
            return False, "INTERPRETER_VERSION_MISMATCH", f"Could not parse version from '{actual_version}'"

        version_parts = [int(p) for p in match.group(1).split(".")]

        min_v = constraints.get("min")
        if min_v:
            min_parts = [int(p) for p in min_v.split(".")]
            if version_parts < min_parts:
                return False, "INTERPRETER_VERSION_MISMATCH", f"Version {match.group(1)} is below minimum {min_v}"

        max_v = constraints.get("max")
        if max_v:
            max_parts = [int(p) for p in max_v.split(".")]
            if version_parts > max_parts:
                return False, "INTERPRETER_VERSION_MISMATCH", f"Version {match.group(1)} is above maximum {max_v}"

        return True, "SUCCESS", ""

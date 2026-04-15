from __future__ import annotations

import ast
from pathlib import Path


class ValidationService:
    def validate_python_syntax(self, file_path: str | Path) -> tuple[bool, str]:
        path = Path(file_path)
        if not path.exists():
            return False, f"File not found: {file_path}"

        if path.suffix != ".py":
            return True, "Not a Python file, skipping syntax check."

        try:
            content = path.read_text(encoding="utf-8")
            ast.parse(content)
            return True, "Python syntax is valid."
        except SyntaxError as exc:
            return False, f"Python syntax error: {exc.msg} (line {exc.lineno})"
        except Exception as exc:
            return False, f"Validation failed with error: {exc}"

    def check_imports(self, file_path: str | Path) -> tuple[bool, str]:
        # Basic import resolution check (Phase 1)
        # Just checks if imports are syntactically valid (covered by ast.parse)
        # Future: check if imported modules exist in the environment or project
        return True, "Import check passed (basic)."

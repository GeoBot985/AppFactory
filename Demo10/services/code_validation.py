from __future__ import annotations

from pathlib import Path

from services.file_ops.models import CodeValidationResult
from services.validators.python_validator import validate_python_syntax


def detect_language(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        return "python"
    return "unknown"


def validate_file_content(path: str, content: str) -> CodeValidationResult:
    language = detect_language(path)
    if language == "python":
        return validate_python_syntax(path, content)
    return CodeValidationResult(
        path=path,
        language=language,
        status="skipped",
        check_name="pass_through",
    )

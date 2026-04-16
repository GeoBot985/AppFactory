from __future__ import annotations

import ast

from services.file_ops.models import CodeValidationResult


def validate_python_syntax(path: str, content: str) -> CodeValidationResult:
    if not content.strip():
        return CodeValidationResult(
            path=path,
            language="python",
            status="invalid",
            error_type="EmptyFileError",
            error_message="python file cannot be empty",
            check_name="non_empty_python_file",
        )

    try:
        tree = ast.parse(content, filename=path)
    except SyntaxError as exc:
        offending = ""
        if exc.text:
            offending = exc.text.rstrip("\n")
        return CodeValidationResult(
            path=path,
            language="python",
            status="invalid",
            error_type=exc.__class__.__name__,
            line_number=exc.lineno or 0,
            column_offset=exc.offset or 0,
            error_message=exc.msg or "syntax error",
            offending_line=offending,
            check_name="ast_parse",
        )

    if not getattr(tree, "body", None):
        return CodeValidationResult(
            path=path,
            language="python",
            status="invalid",
            error_type="EmptyModuleBody",
            error_message="python file must contain at least one statement",
            check_name="module_body",
        )

    return CodeValidationResult(
        path=path,
        language="python",
        status="valid",
        check_name="ast_parse",
    )

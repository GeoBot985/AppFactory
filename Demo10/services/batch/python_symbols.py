from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from services.batch.models import PythonModuleView


def module_path_from_relative_path(relative_path: str) -> str:
    path = Path(relative_path)
    if path.name == "__init__.py":
        parts = path.with_suffix("").parts[:-1]
    else:
        parts = path.with_suffix("").parts
    return ".".join(parts)


def extract_python_module_view(relative_path: str, content: str) -> PythonModuleView:
    module = PythonModuleView(relative_path=relative_path, module_path=module_path_from_relative_path(relative_path))
    try:
        tree = ast.parse(content, filename=relative_path)
    except SyntaxError:
        module.parse_status = "parse_error"
        return module

    names: list[str] = []
    module.parse_status = "parsed"
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                module.imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level:
                mod = "." * node.level + mod
            module.from_imports.setdefault(mod, []).extend(alias.name for alias in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module.functions.append(node.name)
            names.append(node.name)
        elif isinstance(node, ast.ClassDef):
            module.classes.append(node.name)
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)
    counter = Counter(names)
    module.duplicate_symbols = sorted(name for name, count in counter.items() if count > 1)
    return module

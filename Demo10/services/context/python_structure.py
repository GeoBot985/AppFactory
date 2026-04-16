from __future__ import annotations

import ast


def extract_python_structure(content: str) -> dict:
    data = {
        "imports": [],
        "functions": [],
        "classes": [],
        "module_docstring": "",
        "parse_status": "metadata_only",
    }
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return data

    data["parse_status"] = "parsed"
    data["module_docstring"] = ast.get_docstring(tree) or ""
    for node in tree.body:
        if isinstance(node, ast.Import):
            data["imports"].extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = "." * node.level + module
            data["imports"].append(module or "." * node.level)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            data["functions"].append(node.name)
        elif isinstance(node, ast.ClassDef):
            data["classes"].append(node.name)
    data["imports"] = sorted(set(item for item in data["imports"] if item))
    return data

from __future__ import annotations

import re


def normalize_for_comparison(content: str) -> str:
    """
    Normalization strategy:
    - trim trailing whitespace
    - normalize line endings
    - collapse repeated blank lines
    - normalize leading/trailing blank lines
    """
    # Normalize line endings
    content = content.replace("\r\n", "\n")
    # Trim trailing whitespace on each line
    lines = [line.rstrip() for line in content.splitlines()]
    # Join and collapse repeated blank lines
    content = "\n".join(lines)
    content = re.sub(r"\n{3,}", "\n\n", content)
    # Strip leading/trailing blank lines
    return content.strip()


def is_content_equivalent(a: str, b: str) -> bool:
    return normalize_for_comparison(a) == normalize_for_comparison(b)


def is_import_equivalent(import_a: str, import_b: str) -> bool:
    def clean(imp: str):
        imp = imp.strip()
        imp = re.sub(r"#.*$", "", imp).strip()
        return " ".join(imp.split())

    return clean(import_a) == clean(import_b)

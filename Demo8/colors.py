from __future__ import annotations

from models import Node


EXTENSION_GROUPS = {
    "images": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".tiff"},
    "videos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm"},
    "documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".csv"},
    "archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "executables": {".exe", ".msi", ".bat", ".cmd", ".dll", ".so", ".app"},
    "code": {
        ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h", ".hpp",
        ".cs", ".go", ".rs", ".php", ".rb", ".json", ".yaml", ".yml", ".xml", ".html",
        ".css", ".md", ".txt", ".sql",
    },
}

PALETTE = {
    "folder": "#6b7a8f",
    "images": "#8e6ad8",
    "videos": "#d95b5b",
    "documents": "#5b86d9",
    "archives": "#d98a45",
    "executables": "#d9c44f",
    "code": "#5caf6d",
    "unknown": "#8a8f98",
    "error": "#4c4c4c",
}


def color_for_node(node: Node) -> str:
    if node.error:
        return PALETTE["error"]
    if node.is_dir:
        return PALETTE["folder"]
    extension = (node.extension or "").lower()
    for group_name, extensions in EXTENSION_GROUPS.items():
        if extension in extensions:
            return PALETTE[group_name]
    return PALETTE["unknown"]

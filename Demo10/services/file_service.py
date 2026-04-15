from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


TEXT_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".log",
    ".md",
    ".ps1",
    ".py",
    ".rst",
    ".sql",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


@dataclass
class TreeNode:
    name: str
    path: Path
    is_dir: bool
    children: list["TreeNode"] = field(default_factory=list)


class FileService:
    def build_tree(self, root_path: str | Path) -> TreeNode:
        root = Path(root_path).expanduser().resolve()
        return self._build_node(root)

    def _build_node(self, path: Path) -> TreeNode:
        node = TreeNode(name=path.name or str(path), path=path, is_dir=path.is_dir())
        if not node.is_dir:
            return node

        children: list[TreeNode] = []
        try:
            entries = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        except OSError:
            entries = []

        for entry in entries:
            children.append(self._build_node(entry))
        node.children = children
        return node

    def read_text_file(self, file_path: str | Path, max_bytes: int = 1_000_000) -> tuple[bool, str]:
        path = Path(file_path)
        try:
            data = path.read_bytes()
        except OSError as exc:
            return False, f"Unable to read file: {exc}"

        if b"\x00" in data:
            return False, "Binary or unsupported file. Preview unavailable."

        if len(data) > max_bytes:
            data = data[:max_bytes]
            suffix = "\n\n[Preview truncated]"
        else:
            suffix = ""

        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = data.decode("utf-8", errors="replace")
            except Exception:
                return False, "Unreadable text file. Preview unavailable."

        if path.suffix.lower() not in TEXT_EXTENSIONS and "\ufffd" in text:
            return False, "Binary or unsupported file. Preview unavailable."

        return True, text + suffix

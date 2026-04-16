from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from services.context.python_structure import extract_python_structure


INCLUDE_EXTENSIONS = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini"}
EXCLUDED_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", "dist", "build", ".mypy_cache", ".pytest_cache"}
ENTRYPOINT_NAMES = {"main.py", "app.py", "server.py", "cli.py", "run.py"}
CONFIG_NAMES = {"pyproject.toml", "requirements.txt", "package.json", "README.md", "readme.md", "config.yaml", "config.yml"}


@dataclass
class InventoryFile:
    relative_path: str
    absolute_path: str
    extension: str
    size: int
    line_count: int
    is_text: bool
    language: str
    is_entrypoint: bool
    is_config: bool
    structure: dict = field(default_factory=dict)


class WorkspaceInventoryBuilder:
    def build(self, project_root: str | Path) -> list[InventoryFile]:
        root = Path(project_root).expanduser().resolve()
        files: list[InventoryFile] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
                continue
            rel_path = path.relative_to(root).as_posix()
            extension = path.suffix.lower()
            size = path.stat().st_size
            is_text = self._is_text(path, extension)
            language = self._language(extension)
            line_count = 0
            structure = {}
            if is_text:
                try:
                    content = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    content = path.read_text(encoding="utf-8", errors="replace")
                line_count = len(content.splitlines())
                if extension == ".py":
                    structure = extract_python_structure(content)
            files.append(
                InventoryFile(
                    relative_path=rel_path,
                    absolute_path=str(path),
                    extension=extension,
                    size=size,
                    line_count=line_count,
                    is_text=is_text,
                    language=language,
                    is_entrypoint=path.name in ENTRYPOINT_NAMES,
                    is_config=path.name in CONFIG_NAMES or extension in {".json", ".yaml", ".yml", ".toml", ".ini"},
                    structure=structure,
                )
            )
        return files

    def _is_text(self, path: Path, extension: str) -> bool:
        if extension in INCLUDE_EXTENSIONS:
            return True
        try:
            sample = path.read_bytes()[:2048]
        except OSError:
            return False
        return b"\x00" not in sample

    def _language(self, extension: str) -> str:
        mapping = {
            ".py": "python",
            ".md": "markdown",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
            ".ini": "config",
            ".txt": "text",
        }
        return mapping.get(extension, "text")

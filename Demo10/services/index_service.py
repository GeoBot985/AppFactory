from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


TEXT_EXTENSIONS = {
    ".bat",
    ".c",
    ".cmd",
    ".cpp",
    ".css",
    ".go",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


@dataclass
class IndexedFile:
    relative_path: str
    absolute_path: str
    extension: str
    language: str
    module_name: str
    role_tags: list[str]
    imports: list[str]
    top_level_functions: list[str]
    top_level_classes: list[str]
    is_test: bool
    is_entrypoint: bool
    parse_status: str


@dataclass
class ArchitectureIndex:
    project_root: str
    built_at: str
    status: str
    file_count: int
    indexed_file_count: int
    skipped_file_count: int
    parse_error_count: int
    files: list[IndexedFile] = field(default_factory=list)

    def to_preview_text(self) -> str:
        lines = [
            "{",
            f'  "project_root": "{self.project_root}",',
            f'  "built_at": "{self.built_at}",',
            f'  "status": "{self.status}",',
            f'  "file_count": {self.file_count},',
            f'  "indexed_file_count": {self.indexed_file_count},',
            f'  "skipped_file_count": {self.skipped_file_count},',
            f'  "parse_error_count": {self.parse_error_count},',
            '  "files": [',
        ]
        for idx, entry in enumerate(self.files):
            suffix = "," if idx < len(self.files) - 1 else ""
            lines.extend(
                [
                    "    {",
                    f'      "relative_path": "{entry.relative_path}",',
                    f'      "extension": "{entry.extension}",',
                    f'      "language": "{entry.language}",',
                    f'      "module_name": "{entry.module_name}",',
                    f'      "role_tags": {entry.role_tags},',
                    f'      "imports": {entry.imports},',
                    f'      "top_level_functions": {entry.top_level_functions},',
                    f'      "top_level_classes": {entry.top_level_classes},',
                    f'      "is_test": {str(entry.is_test).lower()},',
                    f'      "is_entrypoint": {str(entry.is_entrypoint).lower()},',
                    f'      "parse_status": "{entry.parse_status}"',
                    f"    }}{suffix}",
                ]
            )
        lines.extend(["  ]", "}"])
        return "\n".join(lines)


class IndexBuilder:
    def build(self, project_root: str | Path) -> ArchitectureIndex:
        root = Path(project_root).expanduser().resolve()
        files = sorted(path for path in root.rglob("*") if path.is_file())
        indexed_files: list[IndexedFile] = []
        skipped_file_count = 0
        parse_error_count = 0

        for path in files:
            indexed = self._index_file(root, path)
            if indexed is None:
                skipped_file_count += 1
                continue
            indexed_files.append(indexed)
            if indexed.parse_status == "parse_error":
                parse_error_count += 1

        return ArchitectureIndex(
            project_root=str(root),
            built_at=datetime.now().isoformat(timespec="seconds"),
            status="completed",
            file_count=len(files),
            indexed_file_count=len(indexed_files),
            skipped_file_count=skipped_file_count,
            parse_error_count=parse_error_count,
            files=indexed_files,
        )

    def _index_file(self, root: Path, path: Path) -> IndexedFile | None:
        rel_path = path.relative_to(root).as_posix()
        extension = path.suffix.lower()
        language = self._classify_language(extension)
        module_name = self._module_name(rel_path)
        role_tags = self._role_tags(rel_path)
        is_test = "test" in role_tags
        is_entrypoint = "entrypoint" in role_tags

        if not self._is_text_candidate(path, extension):
            return None

        imports: list[str] = []
        functions: list[str] = []
        classes: list[str] = []
        parse_status = "metadata_only"

        if extension == ".py":
            parse_status, imports, functions, classes = self._parse_python(path)
        elif language != "unknown":
            parse_status = "metadata_only"

        return IndexedFile(
            relative_path=rel_path,
            absolute_path=str(path),
            extension=extension or "(none)",
            language=language,
            module_name=module_name,
            role_tags=role_tags,
            imports=imports,
            top_level_functions=functions,
            top_level_classes=classes,
            is_test=is_test,
            is_entrypoint=is_entrypoint,
            parse_status=parse_status,
        )

    def _parse_python(self, path: Path) -> tuple[str, list[str], list[str], list[str]]:
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return "parse_error", [], [], []
        except OSError:
            return "parse_error", [], [], []

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return "parse_error", self._regex_imports(source), self._regex_defs(source, "def"), self._regex_defs(source, "class")

        imports: list[str] = []
        functions: list[str] = []
        classes: list[str] = []

        for node in tree.body:
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    module = "." * node.level + module
                imports.append(module or "." * node.level)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)

        return "parsed", sorted(set(imports)), functions, classes

    def _regex_imports(self, source: str) -> list[str]:
        imports: list[str] = []
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("import "):
                imports.append(stripped.removeprefix("import ").split(" as ")[0].strip())
            elif stripped.startswith("from "):
                imports.append(stripped.split(" import ", 1)[0].removeprefix("from ").strip())
        return sorted(set(item for item in imports if item))

    def _regex_defs(self, source: str, prefix: str) -> list[str]:
        names: list[str] = []
        token = f"{prefix} "
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith(token):
                names.append(stripped[len(token):].split("(", 1)[0].split(":", 1)[0].strip())
        return names

    def _is_text_candidate(self, path: Path, extension: str) -> bool:
        if extension in TEXT_EXTENSIONS:
            return True
        try:
            data = path.read_bytes()[:2048]
        except OSError:
            return False
        return b"\x00" not in data

    def _classify_language(self, extension: str) -> str:
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".json": "json",
            ".md": "markdown",
            ".ps1": "powershell",
            ".html": "html",
            ".css": "css",
            ".yml": "yaml",
            ".yaml": "yaml",
            ".toml": "toml",
            ".ini": "config",
        }
        return mapping.get(extension, "text" if extension in TEXT_EXTENSIONS else "unknown")

    def _module_name(self, relative_path: str) -> str:
        return relative_path.replace("/", ".").rsplit(".", 1)[0]

    def _role_tags(self, relative_path: str) -> list[str]:
        lower = relative_path.lower()
        tags: set[str] = set()
        filename = Path(lower).name

        if "/tests/" in f"/{lower}/" or filename.startswith("test_") or filename.endswith("_test.py"):
            tags.add("test")
        if filename in {"main.py", "app.py", "run.py", "cli.py"}:
            tags.add("entrypoint")
        if "/ui/" in f"/{lower}/" or "ui" in filename or "view" in filename:
            tags.add("ui")
        if "/services/" in f"/{lower}/" or filename.endswith("_service.py") or "service" in filename:
            tags.add("service")
        if "model" in filename or "/models" in f"/{lower}/":
            tags.add("model")
        if "config" in filename:
            tags.add("config")
        if filename.endswith(".ps1") or filename.endswith(".sh") or filename.endswith(".bat") or "script" in filename:
            tags.add("script")

        return sorted(tags)

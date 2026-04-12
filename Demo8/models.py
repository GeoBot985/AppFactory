from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Node:
    name: str
    path: str
    is_dir: bool
    size: int = 0
    children: list["Node"] = field(default_factory=list)
    extension: str | None = None
    error: str | None = None
    file_count: int = 0
    dir_count: int = 0
    parent: "Node | None" = None

    @property
    def display_name(self) -> str:
        if self.name:
            return self.name
        return self.path or "<root>"

    @property
    def type_name(self) -> str:
        return "Folder" if self.is_dir else "File"

    @classmethod
    def from_file(cls, path: str, size: int, parent: "Node | None" = None) -> "Node":
        extension = Path(path).suffix.lower() or None
        return cls(
            name=Path(path).name,
            path=path,
            is_dir=False,
            size=size,
            extension=extension,
            file_count=1,
            parent=parent,
        )

    @classmethod
    def from_dir(cls, path: str, parent: "Node | None" = None) -> "Node":
        return cls(
            name=Path(path).name,
            path=path,
            is_dir=True,
            parent=parent,
        )


@dataclass(slots=True)
class Rect:
    node: Node
    x: float
    y: float
    w: float
    h: float
    depth: int
    fill: str

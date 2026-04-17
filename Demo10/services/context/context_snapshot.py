from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ContextSnapshot:
    workspace_root: str
    files: List[str] = field(default_factory=list)
    recent_files: List[str] = field(default_factory=list)
    recent_specs: List[str] = field(default_factory=list)
    last_spec_number: Optional[int] = None
    active_directory: str = "."
    known_entry_points: List[str] = field(default_factory=list)

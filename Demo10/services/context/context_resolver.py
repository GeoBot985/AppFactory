from __future__ import annotations
import os
import re
from pathlib import Path
from typing import List, Optional

from .context_snapshot import ContextSnapshot
from .file_inventory import WorkspaceInventoryBuilder
from ..session_memory.session_manager import SessionManager
from ..run_ledger.ledger import LedgerService

class ContextResolver:
    def __init__(self, workspace_root: str, session_manager: SessionManager, ledger_service: LedgerService):
        self.workspace_root = workspace_root
        self.session_manager = session_manager
        self.ledger_service = ledger_service
        self.inventory_builder = WorkspaceInventoryBuilder()

    def capture_snapshot(self) -> ContextSnapshot:
        inventory = self.inventory_builder.build(self.workspace_root)
        files = [f.relative_path for f in inventory]
        entry_points = [f.relative_path for f in inventory if f.is_entrypoint]

        session = self.session_manager.load_or_create_session(self.workspace_root)
        recent_files = []
        if session.working_set:
            recent_files = session.working_set.primary_files

        # Resolve recent specs and last spec number from files and session
        recent_specs = []
        last_spec_num = None

        spec_pattern = re.compile(r"spec_(\d+)")
        spec_files = []
        for f in files:
            match = spec_pattern.search(f)
            if match:
                num = int(match.group(1))
                spec_files.append((num, f))

        if spec_files:
            spec_files.sort(key=lambda x: x[0], reverse=True)
            last_spec_num = spec_files[0][0]
            recent_specs = [f for _, f in spec_files[:5]]

        return ContextSnapshot(
            workspace_root=self.workspace_root,
            files=files,
            recent_files=recent_files,
            recent_specs=recent_specs,
            last_spec_number=last_spec_num,
            active_directory=".", # For now
            known_entry_points=entry_points
        )

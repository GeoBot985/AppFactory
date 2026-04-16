from __future__ import annotations
import os
import json
import uuid
from datetime import datetime
from typing import Optional, Dict
from .models import SessionState, WorkingSet

class SessionManager:
    def __init__(self, persistence_dir: str = "Demo10/runtime_data/session"):
        self.persistence_dir = persistence_dir
        os.makedirs(self.persistence_dir, exist_ok=True)
        self.current_session: Optional[SessionState] = None

    def load_or_create_session(self, workspace_root: str) -> SessionState:
        # Check for existing active session for this workspace
        session_file = self._get_session_file_path(workspace_root)
        if os.path.exists(session_file):
            try:
                with open(session_file, "r") as f:
                    data = json.load(f)
                    self.current_session = SessionState.from_dict(data)
                    # Verify workspace root matches
                    if self.current_session.workspace_root == workspace_root:
                        return self.current_session
            except Exception as e:
                print(f"Failed to load session: {e}")

        # Create new session
        new_session = SessionState(
            session_id=f"sess_{uuid.uuid4().hex[:8]}",
            workspace_root=workspace_root,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        self.current_session = new_session
        self.save_session()
        return new_session

    def save_session(self):
        if not self.current_session:
            return

        self.current_session.updated_at = datetime.now().isoformat()
        session_file = self._get_session_file_path(self.current_session.workspace_root)
        with open(session_file, "w") as f:
            json.dump(self.current_session.to_dict(), f, indent=2)

    def reset_session(self, workspace_root: str):
        # Mark current inactive
        if self.current_session:
            self.current_session.status = "inactive"
            self.save_session()

        # Create new
        self.load_or_create_session(workspace_root)

    def _get_session_file_path(self, workspace_root: str) -> str:
        # Simple hash of workspace root to create a filename
        import hashlib
        ws_hash = hashlib.sha256(workspace_root.encode()).hexdigest()[:12]
        return os.path.join(self.persistence_dir, f"session_{ws_hash}.json")

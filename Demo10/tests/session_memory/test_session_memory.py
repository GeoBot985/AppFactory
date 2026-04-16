from __future__ import annotations
import unittest
import os
import shutil
from pathlib import Path
from Demo10.services.session_memory.models import SessionState, MemoryEntryType
from Demo10.services.session_memory.session_manager import SessionManager
from Demo10.services.session_memory.working_set_manager import WorkingSetManager
from Demo10.services.session_memory.updater import SessionUpdater
from Demo10.services.session_memory.eviction import SessionEvictor

class TestSessionMemory(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("Demo10/runtime_data/test_session")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.session_manager = SessionManager(persistence_dir=str(self.test_dir))
        self.working_set_manager = WorkingSetManager()
        self.updater = SessionUpdater(self.working_set_manager)
        self.evictor = SessionEvictor(max_entries=5)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_session_lifecycle(self):
        ws_root = "/tmp/test_ws"
        session = self.session_manager.load_or_create_session(ws_root)
        self.assertEqual(session.workspace_root, ws_root)
        self.assertEqual(session.status, "active")

        # Record event
        self.updater.record_translation_event(session, "draft_1", "test request", ["file1.py"], None)
        self.session_manager.save_session()

        # Reload
        new_manager = SessionManager(persistence_dir=str(self.test_dir))
        reloaded = new_manager.load_or_create_session(ws_root)
        self.assertEqual(reloaded.session_id, session.session_id)
        self.assertIn("file1.py", reloaded.working_set.primary_files)

    def test_working_set_persistence(self):
        session = self.session_manager.load_or_create_session("/tmp/test_ws")
        self.updater.record_execution_event(session, "run_1", True, ["app.py"], [])
        self.assertIn("app.py", session.working_set.primary_files)

        # Add failure
        self.updater.record_execution_event(session, "run_2", False, [], ["test_app.py"])
        self.assertIn("test_app.py", session.working_set.recent_failure_files)

    def test_eviction(self):
        session = self.session_manager.load_or_create_session("/tmp/test_ws")
        for i in range(10):
            self.updater.record_compile_event(session, f"draft_{i}", f"plan_{i}", True, [])

        self.assertEqual(len(session.memory_entries), 10)
        self.evictor.prune_memory_entries(session)
        self.assertEqual(len(session.memory_entries), 5)

    def test_restore_degrades_confidence(self):
        session = self.session_manager.load_or_create_session("/tmp/test_ws")
        initial_conf = session.working_set.confidence
        self.updater.record_restore_event(session, "restore_1", "run_1")
        self.assertLess(session.working_set.confidence, initial_conf)

if __name__ == "__main__":
    unittest.main()

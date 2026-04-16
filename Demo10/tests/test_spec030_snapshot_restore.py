import unittest
import shutil
import os
import json
from pathlib import Path
from Demo10.workspace.snapshots import SnapshotService
from Demo10.workspace.fingerprints import FingerprintService
from Demo10.workspace.restore_controller import RestoreController
from Demo10.workspace.models import RestoreRequest

class TestSpec030SnapshotRestore(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("test_workspace_spec030")
        self.test_dir.mkdir(exist_ok=True)
        self.storage_root = Path("test_storage_spec030")
        self.storage_root.mkdir(exist_ok=True)

        self.fingerprint_service = FingerprintService()
        self.snapshot_service = SnapshotService(self.fingerprint_service, self.storage_root)
        self.restore_controller = RestoreController(self.snapshot_service, None)

        # Create some files
        (self.test_dir / "file1.txt").write_text("content1")
        (self.test_dir / "dir1").mkdir(exist_ok=True)
        (self.test_dir / "dir1" / "file2.txt").write_text("content2")

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        if self.storage_root.exists():
            shutil.rmtree(self.storage_root)

    def test_snapshot_and_restore(self):
        # 1. Capture snapshot
        snapshot = self.snapshot_service.capture_baseline_snapshot(
            self.test_dir, "run_1", "plan_1"
        )
        self.assertEqual(snapshot.file_count, 2)

        # 2. Mutate workspace
        (self.test_dir / "file1.txt").write_text("content1_modified")
        (self.test_dir / "file3.txt").write_text("content3_new")
        (self.test_dir / "dir1" / "file2.txt").unlink()

        # 3. Execute restore
        request = RestoreRequest(
            request_id="req_1",
            snapshot_id=snapshot.snapshot_id,
            target_workspace=str(self.test_dir),
            requested_by="test",
            reason="test restore"
        )
        restore_run = self.restore_controller.execute_restore(request)

        self.assertEqual(restore_run.status, "completed")
        self.assertEqual(restore_run.verification_status, "verified")
        self.assertEqual(restore_run.files_restored_count, 2) # file1 modified, file2 missing
        self.assertEqual(restore_run.files_removed_count, 1)  # file3 new

        # 4. Verify workspace state
        self.assertEqual((self.test_dir / "file1.txt").read_text(), "content1")
        self.assertTrue((self.test_dir / "dir1" / "file2.txt").exists())
        self.assertEqual((self.test_dir / "dir1" / "file2.txt").read_text(), "content2")
        self.assertFalse((self.test_dir / "file3.txt").exists())

    def test_snapshot_retention(self):
        # Create 12 snapshots
        for i in range(12):
            self.snapshot_service.capture_baseline_snapshot(
                self.test_dir, f"run_{i}", f"plan_{i}"
            )

        # Verify only 10 remain
        remaining = [d for d in self.storage_root.iterdir() if d.is_dir()]
        self.assertEqual(len(remaining), 10)

if __name__ == "__main__":
    unittest.main()

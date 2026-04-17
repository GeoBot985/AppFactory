import unittest
import shutil
import os
import hashlib
from pathlib import Path
from services.apply.changeset import ChangeSetBuilder
from services.apply.conflict_detector import ConflictDetector
from services.apply.executor import DeterministicExecutor
from services.apply.verifier import Verifier
from services.apply.models import ChangeEntry, OperationType, TransactionStatus, ConflictType
from services.file_ops.models import FileOperation

class TestApplyEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("Demo10/test_apply_engine_workspace")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir(parents=True)
        self.builder = ChangeSetBuilder(self.test_dir)
        self.executor = DeterministicExecutor(self.test_dir)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def test_idempotent_create(self):
        # 1. Create a file
        op = FileOperation(
            op_id="op1",
            op_type="create_file",
            path="hello.txt",
            content="Hello World"
        )
        changeset = self.builder.build_changeset("run1", [op])

        tx1 = self.executor.execute(changeset)
        self.assertEqual(tx1.status, TransactionStatus.APPLIED)
        self.assertIn("hello.txt", tx1.applied_files)

        # 2. Run again - should be idempotent
        tx2 = self.executor.execute(changeset)
        self.assertEqual(tx2.status, TransactionStatus.APPLIED)
        self.assertIn("hello.txt", tx2.skipped_files)
        self.assertEqual(len(tx2.applied_files), 0)

    def test_conflict_detection_modified(self):
        # 1. Setup file
        path = self.test_dir / "config.py"
        path.write_text("v1 = 1", encoding="utf-8")
        h1 = self._hash("v1 = 1")

        # 2. Prepare change based on v1
        op = FileOperation(
            op_id="op2",
            op_type="replace_file",
            path="config.py",
            content="v1 = 2"
        )
        changeset = self.builder.build_changeset("run2", [op])

        # 3. Externally modify file
        path.write_text("v1 = 1.5", encoding="utf-8")

        # 4. Execute - should detect conflict
        tx = self.executor.execute(changeset)
        self.assertEqual(tx.status, TransactionStatus.FAILED)
        self.assertTrue(tx.conflict_report.is_blocking)
        self.assertEqual(tx.conflict_report.conflicts[0].conflict_type, ConflictType.HASH_MISMATCH)

    def test_post_apply_verification(self):
        # Mock an executor that fails to write
        class FailingExecutor(DeterministicExecutor):
            def _apply_entry(self, entry):
                return True # Pretend we applied it, but don't actually write

        failing_executor = FailingExecutor(self.test_dir)

        op = FileOperation(
            op_id="op3",
            op_type="create_file",
            path="fail.txt",
            content="I will fail"
        )
        changeset = self.builder.build_changeset("run3", [op])

        tx = failing_executor.execute(changeset)
        self.assertEqual(tx.status, TransactionStatus.FAILED)
        self.assertTrue(any("Verification failed" in e for e in tx.verification_errors))

    def test_rerun_safe(self):
        # 1. Initial Apply
        op = FileOperation(
            op_id="op4",
            op_type="create_file",
            path="rerun.txt",
            content="Initial"
        )
        changeset = self.builder.build_changeset("run4", [op])
        self.executor.execute(changeset)

        # 2. Rerun with same changeset
        tx = self.executor.execute(changeset)
        self.assertEqual(tx.status, TransactionStatus.APPLIED)
        self.assertIn("rerun.txt", tx.skipped_files)

if __name__ == "__main__":
    unittest.main()

import shutil
import unittest
from pathlib import Path

from services.file_ops.executor import FileOperationExecutor
from services.file_ops.models import FileOperation, PatchBlock
from services.task_service import TaskResult


class TestSpec020FileOps(unittest.TestCase):
    def setUp(self):
        self.root = Path("test_spec020_workspace")
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir()
        self.executor = FileOperationExecutor()

    def tearDown(self):
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_create_file_inside_workspace(self):
        result = self.executor.execute(
            self.root,
            [FileOperation(op_id="op1", op_type="create_file", path="src/app.py", content="print('x')\n")],
            mode="apply",
        )
        self.assertEqual(result.failed_count, 0)
        self.assertTrue((self.root / "src" / "app.py").exists())

    def test_reject_path_escape(self):
        result = self.executor.execute(
            self.root,
            [FileOperation(op_id="op1", op_type="create_file", path="..\\outside.py", content="x")],
            mode="apply",
        )
        self.assertEqual(result.status, "failed")
        self.assertFalse((self.root.parent / "outside.py").exists())

    def test_replace_existing_file(self):
        target = self.root / "a.txt"
        target.write_text("old\n", encoding="utf-8")
        result = self.executor.execute(
            self.root,
            [FileOperation(op_id="op1", op_type="replace_file", path="a.txt", content="new\n")],
            mode="apply",
        )
        self.assertEqual(result.modified_count, 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "new\n")

    def test_exact_patch_success(self):
        target = self.root / "a.txt"
        target.write_text("hello world\n", encoding="utf-8")
        result = self.executor.execute(
            self.root,
            [FileOperation(op_id="op1", op_type="patch_file", path="a.txt", patch_blocks=[PatchBlock(match_type="exact", target="world", replacement="agent")])],
            mode="apply",
        )
        self.assertEqual(result.modified_count, 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "hello agent\n")

    def test_exact_patch_target_not_found(self):
        target = self.root / "a.txt"
        target.write_text("hello world\n", encoding="utf-8")
        result = self.executor.execute(
            self.root,
            [FileOperation(op_id="op1", op_type="patch_file", path="a.txt", patch_blocks=[PatchBlock(match_type="exact", target="missing", replacement="agent")])],
            mode="apply",
        )
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "hello world\n")

    def test_regex_patch_ambiguity(self):
        target = self.root / "a.txt"
        target.write_text("one two two\n", encoding="utf-8")
        result = self.executor.execute(
            self.root,
            [FileOperation(op_id="op1", op_type="patch_file", path="a.txt", patch_blocks=[PatchBlock(match_type="regex", target="two", replacement="x", expected_matches=1)])],
            mode="apply",
        )
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.results[0].failure_code, "patch_match_count_mismatch")

    def test_dry_run_mode(self):
        result = self.executor.execute(
            self.root,
            [FileOperation(op_id="op1", op_type="create_file", path="dry.txt", content="hello")],
            mode="dry-run",
        )
        self.assertEqual(result.created_count, 1)
        self.assertFalse((self.root / "dry.txt").exists())

    def test_mixed_batch(self):
        result = self.executor.execute(
            self.root,
            [
                FileOperation(op_id="op1", op_type="create_file", path="good.txt", content="ok"),
                FileOperation(op_id="op2", op_type="replace_file", path="missing.txt", content="no"),
            ],
            mode="apply",
        )
        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.failed_count, 1)
        self.assertTrue((self.root / "good.txt").exists())

    def test_binary_patch_rejection(self):
        target = self.root / "bin.dat"
        target.write_bytes(b"\x00\x01\x02")
        result = self.executor.execute(
            self.root,
            [FileOperation(op_id="op1", op_type="patch_file", path="bin.dat", patch_blocks=[PatchBlock(match_type="exact", target="x", replacement="y")])],
            mode="apply",
        )
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.results[0].failure_code, "binary_file_not_supported")

    def test_ui_result_visibility_model(self):
        result = TaskResult(
            success=True,
            message="ok",
            details={"created_count": 1, "modified_count": 0, "failed_count": 0, "results": [{"path": "a.txt", "status": "created"}]},
        )
        self.assertEqual(result.details["created_count"], 1)
        self.assertEqual(result.details["results"][0]["status"], "created")


if __name__ == "__main__":
    unittest.main()

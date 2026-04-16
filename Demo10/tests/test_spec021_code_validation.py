import shutil
import unittest
from pathlib import Path

from services.file_ops.executor import FileOperationExecutor
from services.file_ops.models import FileOperation, PatchBlock


class TestSpec021CodeValidation(unittest.TestCase):
    def setUp(self):
        self.root = Path("test_spec021_workspace")
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir()
        self.executor = FileOperationExecutor()

    def tearDown(self):
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_valid_python_file_passes(self):
        result = self.executor.execute(
            self.root,
            [FileOperation(op_id="op1", op_type="create_file", path="app.py", content="def run():\n    return 1\n")],
            mode="apply",
        )
        self.assertEqual(result.failed_count, 0)
        self.assertEqual(result.files_validated, 1)
        self.assertEqual(result.files_passed, 1)
        self.assertTrue((self.root / "app.py").exists())

    def test_syntax_error_blocks_write(self):
        result = self.executor.execute(
            self.root,
            [FileOperation(op_id="op1", op_type="create_file", path="bad.py", content="def run()\n    return 1\n")],
            mode="apply",
        )
        self.assertEqual(result.failed_count, 1)
        self.assertFalse((self.root / "bad.py").exists())
        self.assertEqual(result.results[0].failure_code, "code_validation_failed")
        self.assertEqual(result.results[0].validation.error_type, "SyntaxError")
        self.assertEqual(result.results[0].validation.line_number, 1)

    def test_patch_breaks_python_file_and_is_rejected(self):
        target = self.root / "ok.py"
        target.write_text("def run():\n    return 1\n", encoding="utf-8")
        result = self.executor.execute(
            self.root,
            [FileOperation(op_id="op1", op_type="patch_file", path="ok.py", patch_blocks=[PatchBlock(match_type="exact", target="def run():", replacement="def run()")])],
            mode="apply",
        )
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.results[0].validation.error_type, "SyntaxError")
        self.assertEqual(target.read_text(encoding="utf-8"), "def run():\n    return 1\n")

    def test_patch_preserves_validity(self):
        target = self.root / "ok.py"
        target.write_text("def run():\n    return 1\n", encoding="utf-8")
        result = self.executor.execute(
            self.root,
            [FileOperation(op_id="op1", op_type="patch_file", path="ok.py", patch_blocks=[PatchBlock(match_type="exact", target="return 1", replacement="return 2")])],
            mode="apply",
        )
        self.assertEqual(result.failed_count, 0)
        self.assertEqual(result.files_passed, 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "def run():\n    return 2\n")

    def test_empty_python_file_rejected(self):
        result = self.executor.execute(
            self.root,
            [FileOperation(op_id="op1", op_type="create_file", path="empty.py", content="")],
            mode="apply",
        )
        self.assertEqual(result.status, "failed")

    def test_mixed_batch_partial_success(self):
        result = self.executor.execute(
            self.root,
            [
                FileOperation(op_id="good", op_type="create_file", path="good.py", content="x = 1\n"),
                FileOperation(op_id="bad", op_type="create_file", path="bad.py", content="def broken(\n"),
            ],
            mode="apply",
        )
        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.failed_count, 1)
        self.assertTrue((self.root / "good.py").exists())
        self.assertFalse((self.root / "bad.py").exists())

    def test_dry_run_validation_blocks_invalid_write(self):
        result = self.executor.execute(
            self.root,
            [FileOperation(op_id="op1", op_type="create_file", path="dry_bad.py", content="if True print('x')\n")],
            mode="dry-run",
        )
        self.assertEqual(result.failed_count, 1)
        self.assertFalse((self.root / "dry_bad.py").exists())
        self.assertEqual(result.files_failed, 1)

    def test_non_python_file_passes_through(self):
        result = self.executor.execute(
            self.root,
            [FileOperation(op_id="op1", op_type="create_file", path="notes.txt", content="not python\n")],
            mode="apply",
        )
        self.assertEqual(result.failed_count, 0)
        self.assertEqual(result.files_validated, 0)
        self.assertEqual(result.results[0].validation.status, "skipped")


if __name__ == "__main__":
    unittest.main()

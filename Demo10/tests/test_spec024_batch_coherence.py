import shutil
import unittest
from pathlib import Path

from services.file_ops.executor import FileOperationExecutor
from services.file_ops.models import FileOperation
from services.file_ops_service import FileOpsService
from services.ollama_service import OllamaService
from services.process_service import ProcessService
from services.task_executor_service import TaskExecutorService
from services.task_service import Task, TaskType


class StubExecutor(TaskExecutorService):
    def __init__(self, responses, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.responses = list(responses)

    def _call_llm(self, prompt: str) -> str:
        return self.responses.pop(0)


class TestSpec024BatchCoherence(unittest.TestCase):
    def setUp(self):
        self.root = Path("test_spec024_workspace")
        self.run_folder = Path("test_spec024_run")
        for path in (self.root, self.run_folder):
            if path.exists():
                shutil.rmtree(path)
            path.mkdir()
        self.executor = FileOperationExecutor()

    def tearDown(self):
        for path in (self.root, self.run_folder):
            if path.exists():
                shutil.rmtree(path)

    def test_two_file_valid_addition(self):
        (self.root / "app.py").write_text("from helpers import build_prompt\n\nprint(build_prompt())\n", encoding="utf-8")
        result = self.executor.execute(
            self.root,
            [
                FileOperation(op_id="b1", op_type="create_file", path="helpers.py", content="def build_prompt():\n    return 'hi'\n", reason="new helper"),
                FileOperation(op_id="b2", op_type="replace_file", path="app.py", content="from helpers import build_prompt\n\nprint(build_prompt())\n", reason="wire helper"),
            ],
            mode="apply",
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.batch_summary.batch_validation_status, "batch_valid")
        self.assertTrue((self.root / "helpers.py").exists())

    def test_broken_import_target(self):
        (self.root / "app.py").write_text("from helpers import build_prompt\n", encoding="utf-8")
        result = self.executor.execute(
            self.root,
            [
                FileOperation(op_id="b1", op_type="create_file", path="helpers.py", content="def other_name():\n    return 'hi'\n"),
                FileOperation(op_id="b2", op_type="replace_file", path="app.py", content="from helpers import build_prompt\n\nprint(build_prompt())\n"),
            ],
            mode="apply",
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.batch_summary.batch_validation_status, "batch_invalid_broken_import")
        self.assertFalse((self.root / "helpers.py").exists())

    def test_removed_symbol_still_referenced(self):
        (self.root / "helpers.py").write_text("def build_prompt():\n    return 'hi'\n", encoding="utf-8")
        (self.root / "app.py").write_text("from helpers import build_prompt\n\nprint(build_prompt())\n", encoding="utf-8")
        result = self.executor.execute(
            self.root,
            [
                FileOperation(op_id="b1", op_type="replace_file", path="helpers.py", content="def renamed_prompt():\n    return 'hi'\n"),
                FileOperation(op_id="b2", op_type="replace_file", path="app.py", content="from helpers import build_prompt\n\nprint(build_prompt())\n"),
            ],
            mode="apply",
        )
        self.assertEqual(result.batch_summary.batch_validation_status, "batch_invalid_removed_symbol_still_referenced")
        self.assertEqual(result.status, "failed")

    def test_duplicate_symbol_in_same_file(self):
        result = self.executor.execute(
            self.root,
            [FileOperation(op_id="b1", op_type="create_file", path="dup.py", content="def a():\n    return 1\n\ndef a():\n    return 2\n")],
            mode="apply",
        )
        self.assertEqual(result.batch_summary.batch_validation_status, "batch_invalid_duplicate_symbol")
        self.assertFalse((self.root / "dup.py").exists())

    def test_orphan_new_file_warning(self):
        result = self.executor.execute(
            self.root,
            [FileOperation(op_id="b1", op_type="create_file", path="helper.py", content="def util():\n    return 1\n")],
            mode="apply",
        )
        self.assertIn(result.batch_summary.batch_validation_status, {"batch_valid_with_warnings", "batch_valid"})
        self.assertTrue(any("orphan new file" in warning for warning in result.batch_summary.warnings))

    def test_complexity_guard(self):
        ops = [
            FileOperation(op_id=f"b{i}", op_type="create_file", path=f"file_{i}.py", content=f"def f{i}():\n    return {i}\n")
            for i in range(6)
        ]
        result = self.executor.execute(self.root, ops, mode="apply")
        self.assertEqual(result.batch_summary.batch_validation_status, "batch_invalid_unknown")
        self.assertTrue(any("policy_blocked_complex_batch" in reason for reason in result.batch_summary.batch_failure_reasons))

    def test_multi_file_repair_path(self):
        class LoopExecutor(StubExecutor):
            pass

        loop = LoopExecutor(
            ["first-plan", "repair-plan"],
            file_ops=FileOpsService(self.root),
            ollama=OllamaService(),
            process=ProcessService(),
            model_name="test-model",
            run_folder=self.run_folder,
            mutation_mode="apply",
        )
        task = Task(id="repair_batch", type=TaskType.CREATE, target="ignored.py")

        def build_batch(content: str, mode: str):
            if content == "first-plan":
                return loop.file_ops.execute_plan(
                    [
                        FileOperation(op_id="x1", op_type="create_file", path="helpers.py", content="def other_name():\n    return 'hi'\n"),
                        FileOperation(op_id="x2", op_type="create_file", path="app.py", content="from helpers import build_prompt\n\nprint(build_prompt())\n"),
                    ],
                    mode=mode,
                )
            return loop.file_ops.execute_plan(
                [
                    FileOperation(op_id="x1", op_type="create_file", path="helpers.py", content="def build_prompt():\n    return 'hi'\n"),
                    FileOperation(op_id="x2", op_type="create_file", path="app.py", content="from helpers import build_prompt\n\nprint(build_prompt())\n"),
                ],
                mode=mode,
            )

        result, accepted_batch, ledger, _ = loop._run_generation_attempt_loop(
            task=task,
            base_prompt="create helper and wire app",
            supplied_content=None,
            build_batch=build_batch,
        )
        self.assertTrue(result.success)
        self.assertEqual(ledger.attempts[0].failure_class, "batch_invalid_broken_import")
        self.assertEqual(accepted_batch.batch_summary.batch_validation_status, "batch_valid")
        self.assertTrue((self.root / "helpers.py").exists())

    def test_ui_batch_visibility_model(self):
        result = self.executor.execute(
            self.root,
            [
                FileOperation(op_id="b1", op_type="create_file", path="helpers.py", content="def build_prompt():\n    return 'hi'\n"),
                FileOperation(op_id="b2", op_type="create_file", path="app.py", content="from helpers import build_prompt\n\nprint(build_prompt())\n"),
            ],
            mode="dry-run",
        )
        summary = result.batch_summary
        self.assertIsNotNone(summary)
        self.assertEqual(len(summary.target_files), 2)
        self.assertGreaterEqual(len(summary.file_summaries), 2)
        self.assertIn(summary.batch_validation_status, {"batch_valid", "batch_valid_with_warnings"})


if __name__ == "__main__":
    unittest.main()

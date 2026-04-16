import shutil
import unittest
from pathlib import Path

from services.file_ops.models import FileOperation, PatchBlock
from services.file_ops_service import FileOpsService
from services.ollama_service import OllamaService
from services.process_service import ProcessService
from services.task_executor_service import TaskExecutorService
from services.task_service import Task, TaskType


class StubExecutor(TaskExecutorService):
    def __init__(self, responses, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.responses = list(responses)
        self.prompts = []

    def _call_llm(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.responses:
            return ""
        return self.responses.pop(0)


class TestSpec022AttemptLoop(unittest.TestCase):
    def setUp(self):
        self.root = Path("test_spec022_workspace")
        self.run_folder = Path("test_spec022_run")
        for path in (self.root, self.run_folder):
            if path.exists():
                shutil.rmtree(path)
            path.mkdir()

    def tearDown(self):
        for path in (self.root, self.run_folder):
            if path.exists():
                shutil.rmtree(path)

    def _executor(self, responses, mutation_mode="apply"):
        return StubExecutor(
            responses,
            file_ops=FileOpsService(self.root),
            ollama=OllamaService(),
            process=ProcessService(),
            model_name="test-model",
            run_folder=self.run_folder,
            mutation_mode=mutation_mode,
        )

    def test_success_on_first_try(self):
        executor = self._executor(["def run():\n    return 1\n"])
        task = Task(id="t1", type=TaskType.CREATE, target="app.py")
        result = executor.execute(task)
        ledger = result.details["attempt_ledger"]
        self.assertTrue(result.success)
        self.assertEqual(len(ledger.attempts), 1)
        self.assertEqual(ledger.final_outcome, "succeeded_first_try")
        self.assertTrue((self.root / "app.py").exists())

    def test_syntax_error_repaired_on_second_attempt(self):
        executor = self._executor(["def run()\n    return 1\n", "def run():\n    return 2\n"])
        task = Task(id="t2", type=TaskType.CREATE, target="repair.py")
        result = executor.execute(task)
        ledger = result.details["attempt_ledger"]
        self.assertTrue(result.success)
        self.assertEqual(len(ledger.attempts), 2)
        self.assertEqual(ledger.attempts[0].failure_class, "python_syntax_error")
        self.assertEqual(ledger.final_outcome, "succeeded_after_repair")
        self.assertEqual((self.root / "repair.py").read_text(encoding="utf-8"), "def run():\n    return 2\n")

    def test_patch_mismatch_repaired(self):
        target = self.root / "module.py"
        target.write_text("def run():\n    return 1\n", encoding="utf-8")
        executor = self._executor(["bad payload", "def run():\n    return 5\n"])
        task = Task(
            id="t3",
            type=TaskType.MODIFY,
            target="module.py",
            constraints='{"operation":"replace_block","anchor_type":"function","anchor_value":"missing_function"}',
        )
        result = executor.execute(task)
        ledger = result.details["attempt_ledger"]
        self.assertFalse(result.success)
        self.assertEqual(ledger.attempts[0].failure_class, "patch_target_not_found")
        self.assertIn(ledger.attempts[1].attempt_type, {"repair_generate", "full_regenerate"})
        self.assertEqual((self.root / "module.py").read_text(encoding="utf-8"), "def run():\n    return 1\n")

    def test_exhausted_attempts_no_writes(self):
        executor = self._executor(["def run(\n", "def run(\n", "def run(\n"])
        task = Task(id="t4", type=TaskType.CREATE, target="bad.py")
        result = executor.execute(task)
        ledger = result.details["attempt_ledger"]
        self.assertFalse(result.success)
        self.assertEqual(len(ledger.attempts), 3)
        self.assertEqual(ledger.final_outcome, "failed_exhausted_attempts")
        self.assertFalse((self.root / "bad.py").exists())

    def test_nonrepairable_failure_stops_immediately(self):
        executor = self._executor(["print('x')\n"])
        task = Task(id="t5", type=TaskType.CREATE, target="../escape.py")
        result = executor.execute(task)
        ledger = result.details["attempt_ledger"]
        self.assertFalse(result.success)
        self.assertEqual(len(ledger.attempts), 1)
        self.assertEqual(ledger.final_outcome, "failed_nonrepairable")
        self.assertFalse((self.root.parent / "escape.py").exists())

    def test_duplicate_failure_escalates_to_full_regenerate(self):
        executor = self._executor(["def broken(\n", "def broken(\n", "def ok():\n    return 3\n"])
        task = Task(id="t6", type=TaskType.CREATE, target="escalate.py")
        result = executor.execute(task)
        ledger = result.details["attempt_ledger"]
        self.assertTrue(result.success)
        self.assertEqual(ledger.attempts[1].failure_class, "python_syntax_error")
        self.assertEqual(ledger.attempts[2].attempt_type, "full_regenerate")
        self.assertEqual(ledger.final_outcome, "succeeded_after_regenerate")

    def test_ui_attempt_visibility_model(self):
        executor = self._executor(["def broken(\n", "def ok():\n    return 4\n"])
        task = Task(id="t7", type=TaskType.CREATE, target="ui.py")
        result = executor.execute(task)
        ledger = result.details["attempt_ledger"]
        self.assertIn("attempt_ledger", result.details)
        self.assertEqual(ledger.applied_attempt_index, 2)
        self.assertEqual(ledger.attempts[0].attempt_type, "initial_generate")
        self.assertEqual(ledger.attempts[1].attempt_type, "repair_generate")

    def test_controller_can_repair_patch_failure_with_custom_plan_builder(self):
        target = self.root / "patch.py"
        target.write_text("value = 1\n", encoding="utf-8")
        executor = self._executor(["first", "second"], mutation_mode="apply")
        task = Task(id="t8", type=TaskType.CREATE, target="ignored.txt")

        def build_batch(content: str, mode: str):
            if content == "first":
                return executor.file_ops.execute_plan(
                    [FileOperation(op_id="op1", op_type="patch_file", path="patch.py", patch_blocks=[PatchBlock(match_type="exact", target="missing", replacement="value = 2")])],
                    mode=mode,
                )
            return executor.file_ops.execute_plan(
                [FileOperation(op_id="op1", op_type="patch_file", path="patch.py", patch_blocks=[PatchBlock(match_type="exact", target="value = 1", replacement="value = 2")])],
                mode=mode,
            )

        result, accepted_batch, ledger, _ = executor._run_generation_attempt_loop(
            task=task,
            base_prompt="repair patch plan",
            supplied_content=None,
            build_batch=build_batch,
        )
        self.assertTrue(result.success)
        self.assertEqual(ledger.final_outcome, "succeeded_after_repair")
        self.assertEqual((self.root / "patch.py").read_text(encoding="utf-8"), "value = 2\n")
        self.assertIsNotNone(accepted_batch)


if __name__ == "__main__":
    unittest.main()

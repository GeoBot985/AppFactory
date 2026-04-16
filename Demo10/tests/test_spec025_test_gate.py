import shutil
import unittest
from pathlib import Path

from services.file_ops.models import FileOperation
from services.file_ops_service import FileOpsService
from services.ollama_service import OllamaService
from services.process_service import ProcessService
from services.task_executor_service import TaskExecutorService
from services.task_service import Task, TaskType
from services.testing.runner import TestGateRunner


class StubExecutor(TaskExecutorService):
    def __init__(self, responses, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.responses = list(responses)

    def _call_llm(self, prompt: str) -> str:
        return self.responses.pop(0)


class TestSpec025TestGate(unittest.TestCase):
    def setUp(self):
        self.root = Path("test_spec025_workspace")
        self.run_folder = Path("test_spec025_run")
        for path in (self.root, self.run_folder):
            if path.exists():
                shutil.rmtree(path)
            path.mkdir()

    def tearDown(self):
        for path in (self.root, self.run_folder):
            if path.exists():
                shutil.rmtree(path)

    def _write_unittest_project(self, app_body: str, test_body: str | None = None):
        (self.root / "app.py").write_text(app_body, encoding="utf-8")
        tests_dir = self.root / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "test_app.py").write_text(
            test_body
            or (
                "import unittest\n"
                "from app import value\n\n"
                "class AppTests(unittest.TestCase):\n"
                "    def test_value(self):\n"
                "        self.assertEqual(value(), 1)\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
            ),
            encoding="utf-8",
        )

    def test_passing_tests_allow_apply(self):
        self._write_unittest_project("def value():\n    return 1\n")
        service = FileOpsService(self.root)
        result = service.execute_plan(
            [FileOperation(op_id="t1", op_type="replace_file", path="app.py", content="def value():\n    return 1\n")],
            mode="apply",
        )
        self.assertEqual(result.test_summary.status, "passed")
        self.assertTrue((self.root / "app.py").exists())

    def test_failing_tests_block_apply(self):
        self._write_unittest_project("def value():\n    return 1\n")
        service = FileOpsService(self.root)
        result = service.execute_plan(
            [FileOperation(op_id="t2", op_type="replace_file", path="app.py", content="def value():\n    return 2\n")],
            mode="apply",
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.test_summary.failure_class, "test_failure_assertion")
        self.assertEqual((self.root / "app.py").read_text(encoding="utf-8"), "def value():\n    return 1\n")

    def test_test_repair_success(self):
        self._write_unittest_project("def value():\n    return 1\n")
        executor = StubExecutor(
            ["bad", "good"],
            file_ops=FileOpsService(self.root),
            ollama=OllamaService(),
            process=ProcessService(),
            model_name="test-model",
            run_folder=self.run_folder,
            mutation_mode="apply",
        )
        task = Task(id="repair_test", type=TaskType.CREATE, target="ignored.py")

        def build_batch(content: str, mode: str):
            app_content = "def value():\n    return 2\n" if content == "bad" else "def value():\n    return 1\n"
            return executor.file_ops.execute_plan(
                [FileOperation(op_id="t3", op_type="replace_file", path="app.py", content=app_content)],
                mode=mode,
            )

        result, accepted, ledger, _ = executor._run_generation_attempt_loop(task, "fix behavior", None, build_batch)
        self.assertTrue(result.success)
        self.assertEqual(ledger.attempts[0].failure_class, "test_failure_assertion")
        self.assertEqual((self.root / "app.py").read_text(encoding="utf-8"), "def value():\n    return 1\n")
        self.assertEqual(accepted.test_summary.status, "passed")

    def test_repeated_test_failure_exhausts(self):
        self._write_unittest_project("def value():\n    return 1\n")
        executor = StubExecutor(
            ["bad1", "bad2", "bad3"],
            file_ops=FileOpsService(self.root),
            ollama=OllamaService(),
            process=ProcessService(),
            model_name="test-model",
            run_folder=self.run_folder,
            mutation_mode="apply",
        )
        task = Task(id="exhaust_test", type=TaskType.CREATE, target="ignored.py")

        def build_batch(content: str, mode: str):
            return executor.file_ops.execute_plan(
                [FileOperation(op_id="t4", op_type="replace_file", path="app.py", content="def value():\n    return 2\n")],
                mode=mode,
            )

        result, accepted, ledger, _ = executor._run_generation_attempt_loop(task, "fix behavior", None, build_batch)
        self.assertFalse(result.success)
        self.assertIsNone(accepted)
        self.assertEqual(ledger.final_outcome, "failed_exhausted_attempts")
        self.assertEqual((self.root / "app.py").read_text(encoding="utf-8"), "def value():\n    return 1\n")

    def test_import_error_surfaced(self):
        self._write_unittest_project(
            "from missing_module import value\n",
            "import unittest\nimport app\n\nclass AppTests(unittest.TestCase):\n    def test_import(self):\n        self.assertTrue(True)\n",
        )
        runner = TestGateRunner(max_test_duration_seconds=5)
        result = runner.run(self.root, {})
        self.assertEqual(result.status, "failed")
        self.assertIn(result.failure_class, {"module_not_found", "import_error"})

    def test_timeout_handling(self):
        tests_dir = self.root / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "test_sleep.py").write_text(
            "import time\nimport unittest\n\nclass SleepTests(unittest.TestCase):\n    def test_sleep(self):\n        time.sleep(2)\n        self.assertTrue(True)\n",
            encoding="utf-8",
        )
        runner = TestGateRunner(max_test_duration_seconds=1)
        result = runner.run(self.root, {})
        self.assertEqual(result.failure_class, "test_timeout")
        self.assertTrue(result.timed_out)

    def test_no_tests_present_policy(self):
        (self.root / "app.py").write_text("def value():\n    return 1\n", encoding="utf-8")
        runner = TestGateRunner(max_test_duration_seconds=5)
        result = runner.run(self.root, {})
        self.assertEqual(result.status, "passed_with_warnings")
        self.assertTrue(result.no_tests_found)

    def test_ui_visibility_model(self):
        self._write_unittest_project("def value():\n    return 1\n")
        service = FileOpsService(self.root)
        result = service.execute_plan(
            [FileOperation(op_id="t5", op_type="replace_file", path="app.py", content="def value():\n    return 1\n")],
            mode="dry-run",
        )
        self.assertIsNotNone(result.test_summary)
        self.assertIn(result.test_summary.status, {"passed", "passed_with_warnings"})
        self.assertIsInstance(result.test_summary.total_tests, int)


if __name__ == "__main__":
    unittest.main()

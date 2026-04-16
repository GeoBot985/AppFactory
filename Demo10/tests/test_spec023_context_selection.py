import shutil
import unittest
from pathlib import Path

from services.attempts.models import AttemptRecord
from services.context.context_package import ContextPackageBuilder
from services.context.file_excerptor import extract_file_context
from services.context.file_inventory import WorkspaceInventoryBuilder
from services.context.file_selector import select_relevant_files
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
        return self.responses.pop(0)


class TestSpec023ContextSelection(unittest.TestCase):
    def setUp(self):
        self.root = Path("test_spec023_workspace")
        self.run_folder = Path("test_spec023_run")
        for path in (self.root, self.run_folder):
            if path.exists():
                shutil.rmtree(path)
            path.mkdir()
        (self.root / "src").mkdir()
        (self.root / "tests").mkdir()
        (self.root / "__pycache__").mkdir()
        (self.root / ".venv").mkdir()
        (self.root / "src" / "foo.py").write_text("import os\n\ndef build_index():\n    return 1\n", encoding="utf-8")
        (self.root / "src" / "service.py").write_text("def run_service():\n    return 'ok'\n", encoding="utf-8")
        (self.root / "app.py").write_text("from src.foo import build_index\n", encoding="utf-8")
        (self.root / "README.md").write_text("Demo project\n", encoding="utf-8")
        (self.root / "__pycache__" / "junk.pyc").write_bytes(b"\x00\x01")
        (self.root / ".venv" / "script.py").write_text("print('no')\n", encoding="utf-8")
        self.inventory_builder = WorkspaceInventoryBuilder()

    def tearDown(self):
        for path in (self.root, self.run_folder):
            if path.exists():
                shutil.rmtree(path)

    def test_explicit_file_mention_wins(self):
        inventory = self.inventory_builder.build(self.root)
        selected, confidence = select_relevant_files(inventory, "Update src/foo.py to change build_index", [], [], 5)
        self.assertEqual(selected[0].relative_path, "src/foo.py")
        self.assertEqual(selected[0].reason, "explicit_path_match")
        self.assertEqual(confidence, "strong")

    def test_previous_failure_file_retained(self):
        inventory = self.inventory_builder.build(self.root)
        selected, _ = select_relevant_files(inventory, "repair syntax issue", [], ["src/service.py"], 5)
        self.assertEqual(selected[0].relative_path, "src/service.py")
        self.assertEqual(selected[0].reason, "previous_attempt_failure_file")

    def test_large_file_excerpting(self):
        large = self.root / "src" / "large.py"
        large.write_text("\n".join([f"line_{i} = {i}" for i in range(400)]), encoding="utf-8")
        excerpt = extract_file_context(large, "update line_200", 300)
        self.assertEqual(excerpt.mode, "excerpt")
        self.assertLessEqual(excerpt.included_chars, 300)
        self.assertIn("line_200", excerpt.content)

    def test_binary_and_junk_exclusion(self):
        inventory = self.inventory_builder.build(self.root)
        paths = {item.relative_path for item in inventory}
        self.assertNotIn("__pycache__/junk.pyc", paths)
        self.assertNotIn(".venv/script.py", paths)

    def test_context_cap_enforcement(self):
        for idx in range(10):
            (self.root / "src" / f"mod_{idx}.py").write_text(f"def thing_{idx}():\n    return {idx}\n", encoding="utf-8")
        package = ContextPackageBuilder().build(self.root, "update module logic", "initial_generate", [], "")
        self.assertLessEqual(len(package.selected_files), 5)
        self.assertLessEqual(sum(item.included_chars for item in package.selected_files), 12000)

    def test_weak_match_fallback(self):
        package = ContextPackageBuilder().build(self.root, "completely unrelated zebra flux", "initial_generate", [], "")
        self.assertGreaterEqual(len(package.selected_files), 1)
        self.assertEqual(package.selection_confidence, "weak")

    def test_python_structure_extraction(self):
        inventory = self.inventory_builder.build(self.root)
        foo = next(item for item in inventory if item.relative_path == "src/foo.py")
        self.assertIn("build_index", foo.structure["functions"])
        self.assertIn("os", foo.structure["imports"])

    def test_ui_context_visibility_model(self):
        executor = StubExecutor(
            ["def run():\n    return 1\n"],
            file_ops=FileOpsService(self.root),
            ollama=OllamaService(),
            process=ProcessService(),
            model_name="test-model",
            run_folder=self.run_folder,
            mutation_mode="apply",
        )
        task = Task(id="ctx1", type=TaskType.CREATE, target="generated.py")
        result = executor.execute(task)
        package = result.details["context_package"]
        self.assertIsNotNone(package)
        self.assertGreaterEqual(len(package.selected_files), 1)
        self.assertTrue((self.run_folder / "contexts" / "ctx1.json").exists())

    def test_repair_context_uses_prior_history(self):
        builder = ContextPackageBuilder()
        history = [
            AttemptRecord(
                attempt_index=1,
                attempt_type="initial_generate",
                input_summary="x",
                operation_plan_summary="replace_file:src/service.py",
                validation_result_summary="failed",
                failure_class="python_syntax_error",
                targeted_files=["src/service.py"],
                error_summary="expected ':'",
            )
        ]
        package = builder.build(self.root, "repair service", "repair_generate", history, "src/service.py")
        self.assertEqual(package.selected_files[0].relative_path, "src/service.py")
        self.assertEqual(package.selected_files[0].reason, "previous_attempt_failure_file")


if __name__ == "__main__":
    unittest.main()

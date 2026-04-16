import shutil
import unittest
from pathlib import Path

from services.attempts.models import AttemptRecord
from services.file_ops.models import FileOperation
from services.file_ops_service import FileOpsService
from services.ollama_service import OllamaService
from services.process_service import ProcessService
from services.targeting.plan_guard import validate_operation_plan_against_scope
from services.targeting.scope_builder import ScopeBuilder
from services.task_executor_service import TaskExecutorService
from services.task_service import Task, TaskType


class StubExecutor(TaskExecutorService):
    def __init__(self, responses, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.responses = list(responses)
    def _call_llm(self, prompt: str) -> str:
        return self.responses.pop(0)


class TestSpec026TargetingScope(unittest.TestCase):
    def setUp(self):
        self.root = Path("test_spec026_workspace")
        self.run_folder = Path("test_spec026_run")
        for path in (self.root, self.run_folder):
            if path.exists():
                shutil.rmtree(path)
            path.mkdir()
        (self.root / "src").mkdir()
        (self.root / "src" / "service.py").write_text("def run_service():\n    return 'ok'\n", encoding="utf-8")
        (self.root / "src" / "prompting.py").write_text("def build_prompt():\n    return 'x'\n", encoding="utf-8")
        (self.root / "app.py").write_text("from src.prompting import build_prompt\n", encoding="utf-8")
        (self.root / ".venv").mkdir()
        (self.root / ".venv" / "secret.py").write_text("x=1\n", encoding="utf-8")
        self.builder = ScopeBuilder()

    def tearDown(self):
        for path in (self.root, self.run_folder):
            if path.exists():
                shutil.rmtree(path)

    def test_explicit_file_target(self):
        contract = self.builder.build(str(self.root), "t1", "Update src/service.py for bug fix", task_target="src/service.py")
        self.assertEqual(contract.primary_target_files, ["src/service.py"])
        self.assertEqual(contract.scope_policy_result, "scope_allowed")

    def test_explicit_symbol_target(self):
        contract = self.builder.build(str(self.root), "t2", "Update build_prompt behavior")
        self.assertTrue(any(symbol.symbol_name == "build_prompt" and "src/prompting.py" in symbol.file_candidates for symbol in contract.target_symbols))
        self.assertIn("src/prompting.py", contract.primary_target_files)
        self.assertIn("symbol:build_prompt", contract.target_regions["src/prompting.py"])

    def test_read_only_context_separation_and_undeclared_rejection(self):
        contract = self.builder.build(str(self.root), "t3", "Update build_prompt behavior")
        ok, errors = validate_operation_plan_against_scope(
            [FileOperation(op_id="x", op_type="replace_file", path="app.py", content="x")],
            contract,
        )
        self.assertFalse(ok)
        self.assertTrue(any("scope_undeclared_target" in err for err in errors))

    def test_bounded_scope_expansion(self):
        history = [AttemptRecord(attempt_index=1, attempt_type="initial_generate", input_summary="x", operation_plan_summary="y", validation_result_summary="failed", failure_class="batch_invalid_broken_import", targeted_files=["src/service.py"], error_summary="missing import")]
        contract = self.builder.build(str(self.root), "t4", "Update src/service.py", task_target="src/service.py", prior_history=history)
        contract = self.builder.allow_scope_expansion(contract, "src/prompting.py", "missing import from failure", 2)
        self.assertIn("src/prompting.py", contract.secondary_edit_files)
        self.assertEqual(contract.expansion_log[0]["attempt_index"], 2)

    def test_too_broad_task_blocked(self):
        contract = self.builder.build(str(self.root), "t5", "Refactor everything everywhere across repo")
        self.assertTrue(contract.scope_policy_result.startswith("scope_blocked"))

    def test_protected_path_exclusion(self):
        contract = self.builder.build(str(self.root), "t6", "Update secret.py")
        self.assertIn(".venv/secret.py", contract.excluded_files)
        ok, errors = validate_operation_plan_against_scope(
            [FileOperation(op_id="x", op_type="replace_file", path=".venv/secret.py", content="x=2\n")],
            contract,
        )
        self.assertFalse(ok)
        self.assertTrue(any("scope_excluded_file" in err for err in errors))

    def test_ui_targeting_visibility_model(self):
        executor = StubExecutor(
            ["def run():\n    return 1\n"],
            file_ops=FileOpsService(self.root),
            ollama=OllamaService(),
            process=ProcessService(),
            model_name="test-model",
            run_folder=self.run_folder,
            mutation_mode="apply",
        )
        result = executor.execute(Task(id="scope_ui", type=TaskType.CREATE, target="src/service.py"))
        contract = result.details["scope_contract"]
        self.assertIsNotNone(contract)
        self.assertIn("src/service.py", contract.primary_target_files)
        self.assertTrue((self.run_folder / "targeting" / "scope_ui.json").exists())


if __name__ == "__main__":
    unittest.main()

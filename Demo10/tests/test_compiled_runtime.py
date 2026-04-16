import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from services.compiler.models import CompiledPlan, CompileReport, CompileStatus
from services.task_service import Task, TaskType, TaskResult
from services.task_executor_service import TaskExecutorService
from services.compiled_runtime.run_controller import CompiledPlanRunController
from services.compiled_runtime.run_models import CompiledRunStatus, CompiledTaskStatus

class TestCompiledRuntime(unittest.TestCase):
    def setUp(self):
        self.mock_executor = MagicMock(spec=TaskExecutorService)
        self.mock_executor.file_ops = MagicMock()
        self.mock_executor.file_ops.project_root = Path("/tmp/fake")
        self.mock_executor.mutation_mode = "dry-run"
        self.mock_executor.run_folder = Path("/tmp/runs/run1")

        self.controller = CompiledPlanRunController(self.mock_executor)

    def test_simple_plan_executes(self):
        # read_context -> generate_file -> apply
        tasks = [
            Task(id="t1", type=TaskType.READ_CONTEXT, target="."),
            Task(id="t2", type=TaskType.GENERATE_FILE, target="test.py", depends_on=["t1"]),
            Task(id="t3", type=TaskType.APPLY_MUTATIONS, target=".", depends_on=["t2"])
        ]
        plan = CompiledPlan(
            plan_id="p1",
            tasks=tasks,
            execution_graph=["t1", "t2", "t3"],
            policies={"fail_fast": True},
            allowed_targets=["test.py"],
            compile_report=CompileReport(status=CompileStatus.SUCCESS),
            created_at="2023-01-01",
            draft_hash="h1"
        )

        # Mock adapter responses via dispatcher
        with patch('services.compiled_runtime.task_dispatcher.CompiledTaskDispatcher.dispatch') as mock_dispatch:
            def side_effect(task, state, context):
                state.status = CompiledTaskStatus.SUCCEEDED
                return TaskResult(success=True, message="OK")
            mock_dispatch.side_effect = side_effect

            run = self.controller.execute_compiled_plan(plan, "run1")

            self.assertEqual(run.overall_status, CompiledRunStatus.SUCCESS)
            self.assertEqual(run.tasks_succeeded, 3)
            self.assertEqual(mock_dispatch.call_count, 3)

    def test_unsupported_task_type_blocked(self):
        # We need a TaskType that is NOT in ADAPTER_MAP.
        # Currently TaskType.CREATE is not in ADAPTER_MAP (Wait, I added it to map to GenerateFileAdapter)
        # TaskType.VALIDATE is not in ADAPTER_MAP.
        tasks = [
            Task(id="t1", type=TaskType.VALIDATE, target="test.py")
        ]

        plan = CompiledPlan(
            plan_id="p2",
            tasks=tasks,
            execution_graph=["t1"],
            policies={},
            allowed_targets=[],
            compile_report=CompileReport(status=CompileStatus.SUCCESS),
            created_at="",
            draft_hash=""
        )

        run = self.controller.execute_compiled_plan(plan, "run2")
        self.assertEqual(run.overall_status, CompiledRunStatus.FAILED)
        self.assertEqual(run.task_states["t1"].status, CompiledTaskStatus.FAILED)
        self.assertIn("Unsupported task type", run.task_states["t1"].result_summary)

    def test_dependency_order_enforced(self):
        # t2 depends on t1. If t1 fails, t2 should be blocked.
        tasks = [
            Task(id="t1", type=TaskType.READ_CONTEXT, target="."),
            Task(id="t2", type=TaskType.GENERATE_FILE, target="test.py", depends_on=["t1"])
        ]
        plan = CompiledPlan(
            plan_id="p3",
            tasks=tasks,
            execution_graph=["t1", "t2"],
            policies={"fail_fast": True},
            allowed_targets=[],
            compile_report=CompileReport(status=CompileStatus.SUCCESS),
            created_at="",
            draft_hash=""
        )

        with patch('services.compiled_runtime.task_dispatcher.CompiledTaskDispatcher.dispatch') as mock_dispatch:
            def side_effect(task, state, context):
                state.status = CompiledTaskStatus.FAILED
                return TaskResult(success=False, message="Fail")
            mock_dispatch.side_effect = side_effect

            run = self.controller.execute_compiled_plan(plan, "run3")

            self.assertEqual(run.overall_status, CompiledRunStatus.FAILED)
            self.assertEqual(run.task_states["t1"].status, CompiledTaskStatus.FAILED)
            self.assertEqual(run.task_states["t2"].status, CompiledTaskStatus.BLOCKED)

    def test_fail_fast_behavior(self):
        tasks = [
            Task(id="t1", type=TaskType.READ_CONTEXT, target="."),
            Task(id="t2", type=TaskType.READ_CONTEXT, target=".")
        ]
        plan = CompiledPlan(
            plan_id="p4",
            tasks=tasks,
            execution_graph=["t1", "t2"],
            policies={"fail_fast": True},
            allowed_targets=[],
            compile_report=CompileReport(status=CompileStatus.SUCCESS),
            created_at="",
            draft_hash=""
        )

        with patch('services.compiled_runtime.task_dispatcher.CompiledTaskDispatcher.dispatch') as mock_dispatch:
            mock_dispatch.return_value = TaskResult(success=False, message="Fail")

            run = self.controller.execute_compiled_plan(plan, "run4")

            self.assertEqual(run.overall_status, CompiledRunStatus.FAILED)
            self.assertEqual(mock_dispatch.call_count, 1) # Stopped after first failure

if __name__ == "__main__":
    unittest.main()

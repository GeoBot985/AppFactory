import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from services.compiler.models import CompiledPlan, CompileReport, CompileStatus
from services.task_service import Task, TaskType, TaskResult
from services.task_executor_service import TaskExecutorService
from services.compiled_runtime.run_controller import CompiledPlanRunController
from services.compiled_runtime.run_models import CompiledRunStatus, CompiledTaskStatus, CompiledPlanRun, CompiledTaskState
from services.compiled_runtime.rerun_models import ReRunRequest, ReRunType

class TestCompiledRerun(unittest.TestCase):
    def setUp(self):
        self.mock_executor = MagicMock(spec=TaskExecutorService)
        self.mock_executor.file_ops = MagicMock()
        self.mock_executor.file_ops.project_root = Path("/tmp/fake")
        self.mock_executor.mutation_mode = "dry-run"
        self.mock_executor.run_folder = Path("/tmp/runs/run1")

        self.controller = CompiledPlanRunController(self.mock_executor)

    def test_rerun_failed_task(self):
        # p1: t1 (READ_CONTEXT) -> t2 (GENERATE_PATCH) -> t3 (APPLY)
        tasks = [
            Task(id="t1", type=TaskType.READ_CONTEXT, target="."),
            Task(id="t2", type=TaskType.GENERATE_PATCH, target="test.py", depends_on=["t1"]),
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

        # Base run failed at t2
        base_run = CompiledPlanRun(compiled_plan_id="p1", run_id="run1")
        base_run.task_states = {
            "t1": CompiledTaskState(task_id="t1", task_type="READ_CONTEXT", status=CompiledTaskStatus.SUCCEEDED, artifacts={"foo": "bar"}),
            "t2": CompiledTaskState(task_id="t2", task_type="GENERATE_PATCH", status=CompiledTaskStatus.FAILED),
            "t3": CompiledTaskState(task_id="t3", task_type="APPLY_MUTATIONS", status=CompiledTaskStatus.BLOCKED, depends_on=["t2"])
        }

        # Request rerun of failed task
        request = ReRunRequest(base_run_id="run1", rerun_type=ReRunType.RERUN_FAILED_TASK)

        with patch('services.compiled_runtime.task_dispatcher.CompiledTaskDispatcher.dispatch') as mock_dispatch:
            def side_effect(task, state, context):
                state.status = CompiledTaskStatus.SUCCEEDED
                return TaskResult(success=True, message="Fixed")
            mock_dispatch.side_effect = side_effect

            rerun = self.controller.request_rerun(plan, base_run, request)

            self.assertEqual(rerun.overall_status, CompiledRunStatus.SUCCESS)
            self.assertEqual(rerun.tasks_succeeded, 3)
            self.assertEqual(rerun.task_states["t1"].status, CompiledTaskStatus.REUSED)
            self.assertEqual(rerun.task_states["t2"].status, CompiledTaskStatus.RERUN_SUCCEEDED)
            self.assertEqual(rerun.task_states["t3"].status, CompiledTaskStatus.RERUN_SUCCEEDED)
            self.assertEqual(mock_dispatch.call_count, 2) # t2 and t3

    def test_rerun_from_task_invalidates_downstream(self):
        tasks = [
            Task(id="t1", type=TaskType.READ_CONTEXT, target="."),
            Task(id="t2", type=TaskType.GENERATE_PATCH, target="test.py", depends_on=["t1"]),
            Task(id="t3", type=TaskType.APPLY_MUTATIONS, target=".", depends_on=["t2"])
        ]
        plan = CompiledPlan(
            plan_id="p1", tasks=tasks, execution_graph=["t1", "t2", "t3"],
            policies={}, allowed_targets=[], compile_report=CompileReport(status=CompileStatus.SUCCESS),
            created_at="", draft_hash=""
        )

        # Base run was successful, but we want to rerun from t2
        base_run = CompiledPlanRun(compiled_plan_id="p1", run_id="run1")
        base_run.task_states = {
            "t1": CompiledTaskState(task_id="t1", task_type="READ_CONTEXT", status=CompiledTaskStatus.SUCCEEDED),
            "t2": CompiledTaskState(task_id="t2", task_type="GENERATE_PATCH", status=CompiledTaskStatus.SUCCEEDED),
            "t3": CompiledTaskState(task_id="t3", task_type="APPLY_MUTATIONS", status=CompiledTaskStatus.SUCCEEDED)
        }

        request = ReRunRequest(base_run_id="run1", rerun_type=ReRunType.RERUN_FROM_TASK, start_task_id="t2")

        with patch('services.compiled_runtime.task_dispatcher.CompiledTaskDispatcher.dispatch') as mock_dispatch:
            mock_dispatch.return_value = TaskResult(success=True, message="OK")

            rerun = self.controller.request_rerun(plan, base_run, request)

            self.assertEqual(rerun.task_states["t1"].status, CompiledTaskStatus.REUSED)
            self.assertEqual(rerun.task_states["t2"].status, CompiledTaskStatus.RERUN_SUCCEEDED)
            self.assertEqual(rerun.task_states["t3"].status, CompiledTaskStatus.RERUN_SUCCEEDED)
            self.assertEqual(mock_dispatch.call_count, 2)

    def test_stale_plan_blocks_rerun(self):
        plan = CompiledPlan(
            plan_id="p1", tasks=[], execution_graph=[],
            policies={}, allowed_targets=[], compile_report=CompileReport(status=CompileStatus.SUCCESS),
            created_at="", draft_hash="", is_stale=True
        )
        base_run = CompiledPlanRun(compiled_plan_id="p1", run_id="run1")
        request = ReRunRequest(base_run_id="run1", rerun_type=ReRunType.RERUN_FAILED_TASK)

        with self.assertRaises(ValueError) as cm:
            self.controller.request_rerun(plan, base_run, request)
        self.assertIn("stale", str(cm.exception))

if __name__ == "__main__":
    unittest.main()

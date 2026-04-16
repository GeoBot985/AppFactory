from __future__ import annotations
import time
from typing import Optional
from services.task_service import Task, TaskResult, TaskStatus
from services.task_executor_service import TaskExecutorService
from .run_context import SharedRunContext
from .run_models import CompiledTaskState, CompiledTaskStatus
from .task_adapters import ADAPTER_MAP
from .step_artifacts import StepArtifactBundle
from metrics.metrics_service import MetricsService

class CompiledTaskDispatcher:
    def __init__(self, executor: TaskExecutorService, metrics: Optional[MetricsService] = None):
        self.executor = executor
        self.metrics = metrics or getattr(executor, "metrics", None)

    def dispatch(self, task: Task, state: CompiledTaskState, context: SharedRunContext) -> TaskResult:
        adapter = ADAPTER_MAP.get(task.type)
        if not adapter:
            error_msg = f"Unsupported compiled task type: {task.type}"
            state.status = CompiledTaskStatus.FAILED
            state.result_summary = error_msg
            state.failure_class = "unsupported_task_type"
            return TaskResult(success=False, message=error_msg, error="unsupported_task_type")

        state.status = CompiledTaskStatus.RUNNING
        state.started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        state.attempt_count += 1

        if self.metrics:
            self.metrics.start_task(task.id, task.type.value)

        try:
            result = adapter.execute(task, context, self.executor)
            state.status = CompiledTaskStatus.SUCCEEDED if result.success else CompiledTaskStatus.FAILED
            state.result_summary = result.message
            state.failure_class = result.error if not result.success else None
            state.artifacts.update(result.details)

            if self.metrics:
                 self.metrics.end_task(task.id)
                 tm = self.metrics.get_task_metrics(task.id)
            else:
                 tm = None

            # Build artifact bundle
            bundle = StepArtifactBundle(
                run_id="unknown", # Should be passed in or set by controller
                task_id=task.id,
                task_type=task.type.value,
                status=state.status.value,
                input_summary=str(task.constraints),
                output_summary=result.message,
                artifacts=result.details.copy(),
                started_at=state.started_at,
                completed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                metrics=tm.to_dict() if tm else None
            )

            # Add specific refs
            if "mutation_batch" in result.details:
                bundle.mutation_refs.append("last_mutation_batch")
            if task.type.value == "RUN_TESTS":
                bundle.test_refs.append(task.id)
            if "validation" in task.type.value.lower():
                bundle.validation_refs.append(task.id)

            state.bundle = bundle.to_dict()

            # Sync back to original task for legacy UI compatibility
            task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
            task.result = result

            return result
        except Exception as e:
            error_msg = f"Task execution failed with exception: {str(e)}"
            state.status = CompiledTaskStatus.FAILED
            state.result_summary = error_msg
            state.failure_class = "exception"

            task.status = TaskStatus.FAILED
            task.result = TaskResult(success=False, message=error_msg, error=str(e))

            return task.result
        finally:
            state.completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
            task.completed_at = state.completed_at

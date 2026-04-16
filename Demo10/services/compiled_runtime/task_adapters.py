from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from services.task_service import Task, TaskType, TaskResult
from services.task_executor_service import TaskExecutorService
from .run_context import SharedRunContext

class TaskAdapter(ABC):
    @abstractmethod
    def execute(self, task: Task, context: SharedRunContext, executor: TaskExecutorService) -> TaskResult:
        pass

class ReadContextAdapter(TaskAdapter):
    def execute(self, task: Task, context: SharedRunContext, executor: TaskExecutorService) -> TaskResult:
        # We leverage executor's internal logic for context building
        # This is a bit of a hack since executor doesn't have a standalone read_context yet
        # but it uses context_builder internally.
        # For Spec 028, we'll try to use the builder directly if needed,
        # but let's see if we can use executor._run_generation_attempt_loop side effects or similar.
        # Actually, let's just implement a minimal version here or call the service.

        # Conceptually:
        scope_contract = executor.scope_builder.build(
            project_root=str(executor.file_ops.project_root),
            task_id=task.id,
            spec_text=task.constraints or "",
            task_target=task.target,
            prior_history=[]
        )
        context_package = executor.context_builder.build(
            project_root=executor.file_ops.project_root,
            spec_text=task.constraints or "",
            attempt_type="initial_generate",
            prior_history=[],
            task_target=task.target,
            scope_contract=scope_contract
        )
        context.selected_context = context_package
        context.scope_contract = scope_contract

        return TaskResult(
            success=True,
            message=f"Context loaded: {len(context_package.selected_files)} files",
            details={"context_package": context_package}
        )

class GenerateFileAdapter(TaskAdapter):
    def execute(self, task: Task, context: SharedRunContext, executor: TaskExecutorService) -> TaskResult:
        # Map to executor._handle_create
        # We need to ensure it doesn't apply mutations yet if we want a separate apply task.
        # But existing executor.execute(task) with TaskType.CREATE does generate+dry-run or generate+apply
        # based on executor.mutation_mode.

        # To strictly follow Spec 028, we might need to tell executor to NOT apply yet.
        original_mode = executor.mutation_mode
        executor.mutation_mode = "dry-run"
        try:
            result = executor._handle_create(task)
            if result.success:
                batch = result.details.get("mutation_batch")
                if batch:
                    context.candidate_file_ops.extend(batch.results)
            return result
        finally:
            executor.mutation_mode = original_mode

class GeneratePatchAdapter(TaskAdapter):
    def execute(self, task: Task, context: SharedRunContext, executor: TaskExecutorService) -> TaskResult:
        original_mode = executor.mutation_mode
        executor.mutation_mode = "dry-run"
        try:
            result = executor._handle_modify(task)
            if result.success:
                batch = result.details.get("mutation_batch")
                if batch:
                    context.candidate_file_ops.extend(batch.results)
            return result
        finally:
            executor.mutation_mode = original_mode

class RunTestsAdapter(TaskAdapter):
    def execute(self, task: Task, context: SharedRunContext, executor: TaskExecutorService) -> TaskResult:
        # Use executor._handle_run for tests
        result = executor._handle_run(task)
        context.test_results[task.id] = result
        return result

class RunCommandAdapter(TaskAdapter):
    def execute(self, task: Task, context: SharedRunContext, executor: TaskExecutorService) -> TaskResult:
        return executor._handle_run(task)

class ApplyMutationsAdapter(TaskAdapter):
    def execute(self, task: Task, context: SharedRunContext, executor: TaskExecutorService) -> TaskResult:
        if not context.candidate_file_ops:
            return TaskResult(success=True, message="No mutations to apply")

        # Filter out what was already applied if any?
        # For now, apply everything in candidate_file_ops
        batch = executor.file_ops.execute_plan(context.candidate_file_ops, mode="apply")
        context.last_mutation_batch = batch

        if batch.failed_count > 0:
            return TaskResult(success=False, message=f"Failed to apply {batch.failed_count} mutations", details={"batch": batch})

        return TaskResult(success=True, message=f"Successfully applied {len(context.candidate_file_ops)} mutations", details={"batch": batch})

class PythonParseValidationAdapter(TaskAdapter):
    def execute(self, task: Task, context: SharedRunContext, executor: TaskExecutorService) -> TaskResult:
        # For each file in candidate ops that is python, validate it
        from editing.safe_write import SafeWriteService
        sw = SafeWriteService(executor.file_ops.project_root, executor.run_folder or executor.file_ops.project_root)

        errors = []
        for op in context.candidate_file_ops:
            if op.path.endswith(".py") and hasattr(op, "content") and op.content:
                val = sw.validate_python(op.content)
                if not val.syntax_ok:
                    errors.append(f"Syntax error in {op.path}: {val.error_message}")

        if errors:
            return TaskResult(success=False, message="Python parse validation failed", error="; ".join(errors))
        return TaskResult(success=True, message="Python parse validation passed")

class BatchCoherenceAdapter(TaskAdapter):
    def execute(self, task: Task, context: SharedRunContext, executor: TaskExecutorService) -> TaskResult:
        # Placeholder for real batch coherence logic
        return TaskResult(success=True, message="Batch coherence check passed (placeholder)")

# Registry
ADAPTER_MAP = {
    TaskType.READ_CONTEXT: ReadContextAdapter(),
    TaskType.GENERATE_FILE: GenerateFileAdapter(),
    TaskType.GENERATE_PATCH: GeneratePatchAdapter(),
    TaskType.CREATE_FILE: GenerateFileAdapter(),
    TaskType.REPLACE_FILE: GenerateFileAdapter(),
    TaskType.PATCH_FILE: GeneratePatchAdapter(),
    TaskType.RUN_TESTS: RunTestsAdapter(),
    TaskType.RUN: RunCommandAdapter(),
    TaskType.APPLY_MUTATIONS: ApplyMutationsAdapter(),
    TaskType.RUN_PYTHON_PARSE_VALIDATION: PythonParseValidationAdapter(),
    TaskType.RUN_BATCH_COHERENCE_VALIDATION: BatchCoherenceAdapter(),
}

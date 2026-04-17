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

        from services.apply.changeset import ChangeSetBuilder
        from services.apply.executor import DeterministicExecutor
        from services.apply.models import TransactionStatus
        from services.policy.models import PolicyDomain

        builder = ChangeSetBuilder(executor.file_ops.project_root)
        det_executor = DeterministicExecutor(executor.file_ops.project_root)

        # 1. Build ChangeSet
        changeset = builder.build_changeset(getattr(executor, "run_id", "run_unknown"), context.candidate_file_ops)
        context.current_changeset = changeset

        # 2. Policy Check before apply
        if hasattr(executor, "policy_engine"):
            policy_context = {
                "has_conflicts": False, # Will be re-checked if detector finds them
                "file_count": len(changeset.entries)
            }
            # Initial check
            res = executor.policy_engine.evaluate(PolicyDomain.APPLY, changeset.changeset_id, policy_context)
            if res.decision == "block":
                return TaskResult(success=False, message=f"Apply blocked by policy: {', '.join(res.reasons)}")

        # 3. Execute ChangeSet
        transaction = det_executor.execute(changeset)
        context.last_transaction = transaction

        if transaction.status != TransactionStatus.APPLIED:
            msg = f"Failed to apply mutations. Status: {transaction.status.value}"
            if transaction.conflict_report and transaction.conflict_report.conflicts:
                msg += f" | {len(transaction.conflict_report.conflicts)} conflicts detected"
            if transaction.verification_errors:
                msg += f" | {len(transaction.verification_errors)} verification errors"

            return TaskResult(
                success=False,
                message=msg,
                details={
                    "transaction": transaction,
                    "conflicts": transaction.conflict_report,
                    "verification_errors": transaction.verification_errors
                }
            )

        summary = (
            f"Successfully applied {len(transaction.applied_files)} mutations. "
            f"Skipped {len(transaction.skipped_files)} (idempotent)."
        )
        return TaskResult(
            success=True,
            message=summary,
            details={
                "transaction": transaction,
                "applied": transaction.applied_files,
                "skipped": transaction.skipped_files
            }
        )

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

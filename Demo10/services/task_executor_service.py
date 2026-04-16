from __future__ import annotations

import time
import json
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional
from services.attempts.failure_classifier import classify_batch_failure, classify_edit_failure, fingerprint_failure
from services.attempts.models import AttemptConfig, AttemptLedger, AttemptRecord
from services.attempts.repair_prompt_builder import build_repair_input
from services.attempts.strategy_policy import classify_final_outcome, select_next_strategy
from services.context import ContextConfig, ContextPackageBuilder
from services.task_service import Task, TaskType, TaskStatus, TaskResult
from services.file_ops_service import FileOpsService
from services.ollama_service import OllamaService
from services.process_service import ProcessService
from runtime_profiles.commands import CommandExecutor

from editing.models import EditInstruction, OperationType, AnchorType, EditStatus
from editing.anchor_resolver import AnchorResolver
from editing.operations import EditEngine
from editing.safe_write import SafeWriteService
from editing.diffing import generate_unified_diff, save_diff
from services.file_ops.models import FileOperation


class TaskExecutorService:
    def __init__(
        self,
        file_ops: FileOpsService,
        ollama: OllamaService,
        process: ProcessService,
        model_name: str,
        run_folder: Optional[Path] = None,
        cmd_executor: Optional[CommandExecutor] = None,
        mutation_mode: str = "apply",
    ):
        self.file_ops = file_ops
        self.ollama = ollama
        self.process = process
        self.model_name = model_name
        self.run_folder = run_folder
        self.cmd_executor = cmd_executor
        self.mutation_mode = mutation_mode
        self.edit_engine = EditEngine(AnchorResolver())
        self.attempt_config = AttemptConfig()
        self.context_builder = ContextPackageBuilder(ContextConfig())

    def execute(self, task: Task) -> TaskResult:
        task.status = TaskStatus.RUNNING
        task.started_at = self._now()

        try:
            if task.type == TaskType.CREATE:
                result = self._handle_create(task)
            elif task.type == TaskType.MODIFY:
                result = self._handle_modify(task)
            elif task.type == TaskType.DELETE:
                result = self._handle_delete(task)
            elif task.type == TaskType.RUN:
                result = self._handle_run(task)
            elif task.type == TaskType.VALIDATE:
                result = self._handle_validate(task)
            else:
                result = TaskResult(success=False, message=f"Unknown task type: {task.type}")
        except Exception as exc:
            result = TaskResult(success=False, message=f"Task failed with exception: {exc}", error=str(exc))

        task.result = result
        task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
        task.completed_at = self._now()
        return result

    def _handle_create(self, task: Task) -> TaskResult:
        base_prompt = f"Generate code for the file '{task.target}' based on these constraints: {task.constraints or 'none'}. Output ONLY the code, no markdown markers."

        def build_batch(content: str, mode: str):
            return self.file_ops.execute_plan(
                [
                    FileOperation(
                        op_id=task.id,
                        op_type="create_file",
                        path=task.target,
                        content=content,
                        reason=task.constraints or "",
                        source_stage="task_executor.create",
                    )
                ],
                mode=mode,
            )

        result, accepted_batch, ledger, _ = self._run_generation_attempt_loop(
            task=task,
            base_prompt=base_prompt,
            supplied_content=task.content,
            build_batch=build_batch,
        )
        mutation_batch = result.details.get("mutation_batch")
        if mutation_batch:
            self._write_mutation_artifacts(task.id, mutation_batch)
        self._write_attempt_artifacts(task.id, ledger)
        self.write_context_artifact(task.id, result.details.get("context_package"))
        return result

    def _handle_modify(self, task: Task) -> TaskResult:
        # SPEC 011 New modify flow
        instr = self._get_edit_instruction(task)
        if not instr:
            # Fallback to legacy if no structured instruction found
            return self._handle_modify_legacy(task)

        target_path = self.file_ops._safe_path(task.target)
        if not target_path.exists():
             return TaskResult(success=False, message=f"File not found: {task.target}")

        old_content = target_path.read_text(encoding="utf-8")
        lines = target_path.read_text(encoding="utf-8").splitlines(keepends=True)

        base_prompt = f"Generate the content/payload for this edit task on '{task.target}': {task.constraints}. Output ONLY the new code block, no markdown markers."

        def build_batch(payload: str, mode: str):
            instr.payload = payload
            new_lines, edit_result = self.edit_engine.apply(lines, instr)
            if edit_result.status == EditStatus.FAILED:
                failure_class, failure_detail = classify_edit_failure(edit_result.reason)
                record = AttemptRecord(
                    attempt_index=0,
                    attempt_type="",
                    input_summary=f"payload_len={len(payload)}",
                    operation_plan_summary=f"{instr.operation.value}:{task.target}",
                    validation_result_summary="edit_engine_failed",
                    failure_class=failure_class,
                    error_summary=failure_detail,
                    targeted_files=[task.target],
                    failure_fingerprint=fingerprint_failure(failure_class, failure_detail, task.target),
                )
                return None, edit_result, record

            if edit_result.status == EditStatus.NO_OP:
                batch = self.file_ops.execute_plan([], mode="dry-run")
                batch.status = "completed"
                return batch, edit_result, None

            new_content = "".join(new_lines)

            # Safe Write & Backup
            if self.run_folder:
                sw = SafeWriteService(self.file_ops.project_root, self.run_folder)

                # Backup
                edit_result.backup_path = str(sw.backup(task.target))

                # Validation
                val = sw.validate_python(new_content)
                edit_result.validation = val
                if not val.syntax_ok:
                    batch = self.file_ops.execute_plan(
                        [
                            FileOperation(
                                op_id=task.id,
                                op_type="replace_file",
                                path=task.target,
                                content=new_content,
                                reason=edit_result.reason,
                                source_stage="task_executor.modify",
                            )
                        ],
                        mode="dry-run",
                    )
                    return batch, edit_result, None

                # Symbol validation if applicable
                if instr.operation in [OperationType.ENSURE_FUNCTION, OperationType.REPLACE_BLOCK] and instr.anchor_type == AnchorType.FUNCTION:
                    if not sw.verify_symbol(new_content, instr.anchor_value, "function"):
                        batch = self.file_ops.execute_plan(
                            [
                                FileOperation(
                                    op_id=task.id,
                                    op_type="replace_file",
                                    path=task.target,
                                    content=new_content,
                                    reason=f"symbol validation failed: function {instr.anchor_value} missing after edit",
                                    source_stage="task_executor.modify",
                                )
                            ],
                            mode="dry-run",
                        )
                        return batch, edit_result, None

                # Diff
                diff_text = generate_unified_diff(old_content, new_content, task.target)
                edit_result.diff_path = str(save_diff(self.run_folder, task.target, diff_text))

            batch = self.file_ops.execute_plan(
                [
                    FileOperation(
                        op_id=task.id,
                        op_type="replace_file",
                        path=task.target,
                        content=new_content,
                        reason=edit_result.reason,
                        source_stage="task_executor.modify",
                    )
                ],
                mode=mode,
            )
            return batch, edit_result, None

        result, accepted_batch, ledger, extra_details = self._run_generation_attempt_loop(
            task=task,
            base_prompt=base_prompt,
            supplied_content=task.content,
            build_batch=build_batch,
        )
        mutation_batch = result.details.get("mutation_batch")
        if mutation_batch:
            self._write_mutation_artifacts(task.id, mutation_batch)
        self._write_attempt_artifacts(task.id, ledger)
        self.write_context_artifact(task.id, result.details.get("context_package"))
        if extra_details and result.success:
            result.details["edit_result"] = extra_details.get("edit_result")
        return result

    def _get_edit_instruction(self, task: Task) -> Optional[EditInstruction]:
        if not task.constraints:
            return None
        try:
            data = json.loads(task.constraints)
            if "operation" in data and "anchor_type" in data:
                return EditInstruction(
                    task_id=task.id,
                    file_path=task.target,
                    operation=OperationType(data["operation"]),
                    anchor_type=AnchorType(data["anchor_type"]),
                    anchor_value=data.get("anchor_value", ""),
                    payload=""
                )
        except:
            pass
        return None

    def _handle_modify_legacy(self, task: Task) -> TaskResult:
        base_prompt = f"Modify the file '{task.target}' based on these constraints: {task.constraints or 'none'}. Output ONLY the new content for the file, no markdown markers."

        def build_batch(content: str, mode: str):
            return self.file_ops.execute_plan(
                [
                    FileOperation(
                        op_id=task.id,
                        op_type="replace_file",
                        path=task.target,
                        content=content,
                        reason=task.constraints or "",
                        source_stage="task_executor.modify_legacy",
                    )
                ],
                mode=mode,
            )

        result, accepted_batch, ledger, _ = self._run_generation_attempt_loop(
            task=task,
            base_prompt=base_prompt,
            supplied_content=task.content,
            build_batch=build_batch,
        )
        mutation_batch = result.details.get("mutation_batch")
        if mutation_batch:
            self._write_mutation_artifacts(task.id, mutation_batch)
        self._write_attempt_artifacts(task.id, ledger)
        self.write_context_artifact(task.id, result.details.get("context_package"))
        return result

    def _handle_delete(self, task: Task) -> TaskResult:
        batch = self.file_ops.execute_plan(
            [
                FileOperation(
                    op_id=task.id,
                    op_type="delete_file",
                    path=task.target,
                    source_stage="task_executor.delete",
                )
            ],
            mode=self.mutation_mode,
        )
        self._write_mutation_artifacts(task.id, batch)
        if batch.failed_count:
            return TaskResult(success=False, message=batch.results[0].failure_reason or "delete failed", details={"mutation_batch": batch})
        return TaskResult(success=True, message=f"Deleted {task.target}; {batch.to_summary()}", changes=[task.target], details={"mutation_batch": batch})

    def _run_generation_attempt_loop(
        self,
        task: Task,
        base_prompt: str,
        supplied_content: str | None,
        build_batch: Callable[[str, str], object],
    ):
        history: list[AttemptRecord] = []
        last_batch = None
        last_extra = None
        last_context_package = None
        stop_reason = ""
        accepted_batch = None
        generated_content = supplied_content
        next_strategy = "initial_generate"

        if supplied_content is not None:
            batch, extra, prebuilt_attempt = self._normalize_attempt_output(build_batch(supplied_content, self.mutation_mode))
            if self._is_batch_success(batch):
                accepted_batch = batch
                record = AttemptRecord(
                    attempt_index=1,
                    attempt_type="initial_generate",
                    input_summary=f"supplied_content_len={len(supplied_content)}",
                    operation_plan_summary=self._summarize_batch(batch),
                    validation_result_summary=self._summarize_validation(batch),
                    success=True,
                    stop_reason="supplied_content_valid",
                    targeted_files=self._targeted_files(batch),
                    diff_preview_summary=self._summarize_diff(batch),
                    disk_write_performed=self.mutation_mode == "apply",
                    context_summary="supplied_content_no_context_build",
                )
                history.append(record)
                result = TaskResult(success=True, message=f"Applied {task.target}; {batch.to_summary()}", changes=[task.target], details={"mutation_batch": batch, "attempt_ledger": AttemptLedger(attempts=history, final_outcome="succeeded_first_try", applied_attempt_index=1, stopped_reason="success"), "context_package": None})
                return result, accepted_batch, AttemptLedger(attempts=history, final_outcome="succeeded_first_try", applied_attempt_index=1, stopped_reason="success"), {"edit_result": extra} if extra else None
            detail = "generation failed"
            failure_class = "unknown_validation_failure"
            if prebuilt_attempt:
                failure_class = prebuilt_attempt.failure_class
                detail = prebuilt_attempt.error_summary or detail
            elif batch:
                failure_class, detail = classify_batch_failure(batch)
            history.append(
                AttemptRecord(
                    attempt_index=1,
                    attempt_type="initial_generate",
                    input_summary=f"supplied_content_len={len(supplied_content)}",
                    operation_plan_summary=self._summarize_batch(batch) if batch else task.target,
                    validation_result_summary=self._summarize_validation(batch) if batch else "failed",
                    failure_class=failure_class,
                    repair_strategy_used="supplied_content",
                    success=False,
                    stop_reason="supplied_content_failed",
                    targeted_files=[task.target],
                    diff_preview_summary=self._summarize_diff(batch) if batch else "",
                    error_summary=detail,
                    failure_fingerprint=fingerprint_failure(failure_class, detail, task.target),
                    context_summary="supplied_content_no_context_build",
                )
            )
            ledger = AttemptLedger(attempts=history, final_outcome="failed_policy_blocked", applied_attempt_index=0, stopped_reason="supplied_content_failed")
            message = detail or "generation failed"
            return TaskResult(success=False, message=message, details={"mutation_batch": batch, "attempt_ledger": ledger, "context_package": None}), None, ledger, {"edit_result": extra} if extra else None

        for attempt_index in range(1, self.attempt_config.max_total_attempts + 1):
            attempt_type = next_strategy
            context_package = self.context_builder.build(
                project_root=self.file_ops.project_root,
                spec_text=base_prompt,
                attempt_type=attempt_type,
                prior_history=history,
                task_target=task.target,
            )
            last_context_package = context_package
            prompt = f"{base_prompt}\n\n{self.context_builder.to_prompt_text(context_package)}"
            if attempt_index > 1:
                prior = history[-1]
                prompt = (
                    build_repair_input(task.target, base_prompt, prior.failure_class, prior.error_summary, history, next_strategy)
                    + "\n\n"
                    + self.context_builder.to_prompt_text(context_package)
                )
            generated_content = self._call_llm(prompt)
            batch, extra, prebuilt_attempt = self._normalize_attempt_output(build_batch(generated_content, "dry-run"))
            last_batch = batch
            last_extra = extra

            if prebuilt_attempt:
                record = prebuilt_attempt
                record.attempt_index = attempt_index
                record.attempt_type = attempt_type
                record.repair_strategy_used = next_strategy
                record.validation_result_summary = "failed"
                record.context_summary = self._summarize_context(context_package)
            else:
                failure_class = ""
                error_detail = ""
                success = self._is_batch_success(batch)
                if not success:
                    failure_class, error_detail = classify_batch_failure(batch)
                validation = self._summarize_validation(batch) if batch else "failed"
                fingerprint = ""
                if not success:
                    path = batch.results[0].path if batch and batch.results else task.target
                    line = 0
                    column = 0
                    if batch and batch.results and batch.results[0].validation:
                        line = batch.results[0].validation.line_number
                        column = batch.results[0].validation.column_offset
                    fingerprint = fingerprint_failure(failure_class, error_detail, path, line, column)
                record = AttemptRecord(
                    attempt_index=attempt_index,
                    attempt_type=next_strategy,
                    input_summary=f"prompt_len={len(prompt)} generated_len={len(generated_content)}",
                    operation_plan_summary=self._summarize_batch(batch) if batch else task.target,
                    validation_result_summary=validation,
                    failure_class=failure_class,
                    repair_strategy_used=next_strategy,
                    success=success,
                    stop_reason="success" if success else "",
                    targeted_files=self._targeted_files(batch) if batch else [task.target],
                    diff_preview_summary=self._summarize_diff(batch) if batch else "",
                    error_summary=error_detail,
                    failure_fingerprint=fingerprint,
                    context_summary=self._summarize_context(context_package),
                )
            history.append(record)

            if record.success and batch:
                accepted_batch = batch
                if self.mutation_mode == "apply":
                    accepted_batch, extra, _ = self._normalize_attempt_output(build_batch(generated_content, "apply"))
                history[-1].disk_write_performed = self.mutation_mode == "apply"
                history[-1].stop_reason = "accepted_after_validation"
                final_outcome = classify_final_outcome(history, True, "success")
                ledger = AttemptLedger(attempts=history, final_outcome=final_outcome, applied_attempt_index=attempt_index, stopped_reason="success")
                message = self._success_message_for_task(task, accepted_batch, final_outcome)
                details = {"mutation_batch": accepted_batch, "attempt_ledger": ledger, "context_package": context_package}
                return TaskResult(success=True, message=message, changes=[task.target], details=details), accepted_batch, ledger, {"edit_result": extra} if extra else None

            strategy, strategy_reason = select_next_strategy(self.attempt_config, history, history[-1].failure_class)
            history[-1].stop_reason = strategy_reason
            if strategy == "abort_nonrepairable":
                stop_reason = "nonrepairable"
                break
            if strategy == "abort_exhausted":
                stop_reason = "exhausted"
                break
            next_strategy = strategy

        final_outcome = classify_final_outcome(history, False, stop_reason or "exhausted")
        ledger = AttemptLedger(attempts=history, final_outcome=final_outcome, applied_attempt_index=0, stopped_reason=stop_reason or "exhausted")
        details = {"mutation_batch": last_batch, "attempt_ledger": ledger, "context_package": last_context_package}
        message = history[-1].error_summary if history else "generation failed"
        return TaskResult(success=False, message=message or "generation failed", error=history[-1].failure_class if history else "", details=details), None, ledger, {"edit_result": last_extra} if last_extra else None

    def _success_message_for_task(self, task: Task, batch, final_outcome: str) -> str:
        if task.type == TaskType.CREATE:
            return f"Created {task.target}; {batch.to_summary()}; outcome={final_outcome}"
        if task.type == TaskType.MODIFY:
            return f"File modified: {task.target}; {batch.to_summary()}; outcome={final_outcome}"
        return f"Applied {task.target}; {batch.to_summary()}; outcome={final_outcome}"

    def _summarize_batch(self, batch) -> str:
        if not batch:
            return "no_batch"
        ops = ", ".join(f"{item.op_type}:{item.path}" for item in batch.results) or "no_results"
        return f"{batch.status}; {ops}"

    def _summarize_validation(self, batch) -> str:
        if not batch:
            return "not_validated"
        if batch.files_validated:
            return f"validated={batch.files_validated}, passed={batch.files_passed}, failed={batch.files_failed}"
        return "validation_skipped"

    def _summarize_diff(self, batch) -> str:
        if not batch or not batch.results:
            return ""
        previews = [item.diff_preview[:240] for item in batch.results if item.diff_preview]
        return "\n\n".join(previews[:3])

    def _targeted_files(self, batch) -> list[str]:
        if not batch:
            return []
        return [item.path for item in batch.results]

    def _is_batch_success(self, batch) -> bool:
        if not batch:
            return False
        return not batch.validation_errors and batch.failed_count == 0 and batch.status == "completed"

    def _normalize_attempt_output(self, output):
        if isinstance(output, tuple):
            if len(output) == 3:
                return output
            if len(output) == 2:
                return output[0], output[1], None
        return output, None, None

    def _summarize_context(self, package) -> str:
        return f"files={len(package.selected_files)}, confidence={package.selection_confidence}"

    def _handle_run(self, task: Task) -> TaskResult:
        if self.cmd_executor:
            timeout = None
            if task.constraints:
                try:
                    data = json.loads(task.constraints)
                    if "runtime_override" in data:
                        timeout = data["runtime_override"].get("timeout_seconds")
                except:
                    pass

            res = self.cmd_executor.run(task.target, timeout_seconds=timeout)

            # Log command artifact if run_folder exists
            if self.run_folder:
                cmd_dir = self.run_folder / "commands"
                cmd_dir.mkdir(parents=True, exist_ok=True)

                cmd_id = task.id
                (cmd_dir / f"{cmd_id}.stdout.txt").write_text(res.stdout, encoding="utf-8")
                (cmd_dir / f"{cmd_id}.stderr.txt").write_text(res.stderr, encoding="utf-8")

                import json
                info = {
                    "task_id": cmd_id,
                    "command": res.command,
                    "cwd": res.cwd,
                    "profile_id": res.profile_id,
                    "exit_code": res.exit_code,
                    "duration_ms": res.duration_ms,
                    "timeout_reached": res.timeout_reached
                }
                (cmd_dir / f"{cmd_id}.json").write_text(json.dumps(info, indent=2), encoding="utf-8")

            return TaskResult(
                success=res.exit_code == 0,
                message=f"Command finished with exit code {res.exit_code}",
                output=res.stdout,
                error=res.stderr
            )

        # Legacy fallback
        import subprocess
        try:
            process = subprocess.run(
                task.target,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(self.file_ops.project_root)
            )
            success = process.returncode == 0
            return TaskResult(
                success=success,
                message=f"Command finished with exit code {process.returncode}",
                output=process.stdout,
                error=process.stderr
            )
        except Exception as exc:
            return TaskResult(success=False, message=f"Command execution failed: {exc}", error=str(exc))

    def _handle_validate(self, task: Task) -> TaskResult:
        # Placeholder for external validator call
        # In Phase 1, we might use a dedicated ValidationService
        return TaskResult(success=True, message=f"Validation '{task.target}' passed (placeholder)")

    def _call_llm(self, prompt: str) -> str:
        snapshot = self.ollama.create_snapshot(self.model_name, prompt)
        accumulator = []
        for event in self.ollama.run_prompt_stream(snapshot):
            if event["type"] == "chunk":
                accumulator.append(event["text"])
            elif event["type"] == "done":
                break
        return "".join(accumulator).strip()

    def _write_mutation_artifacts(self, task_id: str, batch_result) -> None:
        if not self.run_folder:
            return
        mutations_dir = self.run_folder / "mutations"
        mutations_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "project_root": batch_result.project_root,
            "mode": batch_result.mode,
            "status": batch_result.status,
            "created_count": batch_result.created_count,
            "modified_count": batch_result.modified_count,
            "deleted_count": batch_result.deleted_count,
            "unchanged_count": batch_result.unchanged_count,
            "failed_count": batch_result.failed_count,
            "files_validated": batch_result.files_validated,
            "files_passed": batch_result.files_passed,
            "files_failed": batch_result.files_failed,
            "validation_errors": batch_result.validation_errors,
            "batch_summary": asdict(batch_result.batch_summary) if batch_result.batch_summary else None,
            "test_summary": asdict(batch_result.test_summary) if batch_result.test_summary else None,
            "results": [asdict(result) for result in batch_result.results],
            "ledger": [asdict(entry) for entry in batch_result.ledger],
        }
        (mutations_dir / f"{task_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_attempt_artifacts(self, task_id: str, ledger: AttemptLedger) -> None:
        if not self.run_folder:
            return
        attempts_dir = self.run_folder / "attempts"
        attempts_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "final_outcome": ledger.final_outcome,
            "applied_attempt_index": ledger.applied_attempt_index,
            "stopped_reason": ledger.stopped_reason,
            "attempts": [asdict(item) for item in ledger.attempts],
        }
        (attempts_dir / f"{task_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def write_context_artifact(self, task_id: str, context_package) -> None:
        if not self.run_folder or context_package is None:
            return
        context_dir = self.run_folder / "contexts"
        context_dir.mkdir(parents=True, exist_ok=True)
        payload = self.context_builder.to_dict(context_package)
        (context_dir / f"{task_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S")

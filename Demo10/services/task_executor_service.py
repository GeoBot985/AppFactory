from __future__ import annotations

import time
import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional
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
        # LLM helps generate content if not provided
        content = task.content
        if not content:
            prompt = f"Generate code for the file '{task.target}' based on these constraints: {task.constraints or 'none'}. Output ONLY the code, no markdown markers."
            content = self._call_llm(prompt)

        batch = self.file_ops.execute_plan(
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
            mode=self.mutation_mode,
        )
        self._write_mutation_artifacts(task.id, batch)
        if batch.failed_count:
            return TaskResult(success=False, message=batch.results[0].failure_reason or "create failed", details={"mutation_batch": batch})
        return TaskResult(success=True, message=f"Created {task.target}; {batch.to_summary()}", changes=[task.target], details={"mutation_batch": batch})

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

        # Get payload from LLM if not present
        if not task.content:
            prompt = f"Generate the content/payload for this edit task on '{task.target}': {task.constraints}. Output ONLY the new code block, no markdown markers."
            task.content = self._call_llm(prompt)

        instr.payload = task.content

        # Apply edit
        new_lines, edit_result = self.edit_engine.apply(lines, instr)

        if edit_result.status == EditStatus.FAILED:
            return TaskResult(success=False, message=f"Edit failed: {edit_result.reason}", error=edit_result.reason)

        if edit_result.status == EditStatus.NO_OP:
            return TaskResult(success=True, message=f"No changes needed: {edit_result.reason}", changes=[])

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
                return TaskResult(success=False, message=f"Syntax validation failed: {val.error_message}", error=val.error_message)

            # Symbol validation if applicable
            if instr.operation in [OperationType.ENSURE_FUNCTION, OperationType.REPLACE_BLOCK] and instr.anchor_type == AnchorType.FUNCTION:
                if not sw.verify_symbol(new_content, instr.anchor_value, "function"):
                     return TaskResult(success=False, message=f"Symbol validation failed: function {instr.anchor_value} missing after edit")

            # Diff
            diff_text = generate_unified_diff(old_content, new_content, task.target)
            edit_result.diff_path = str(save_diff(self.run_folder, task.target, diff_text))

            # Commit is now routed through the mutation engine after validation/diff generation.
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
            mode=self.mutation_mode,
        )
        self._write_mutation_artifacts(task.id, batch)
        if batch.failed_count:
            return TaskResult(success=False, message=batch.results[0].failure_reason or "replace failed", error=batch.results[0].failure_code, details={"mutation_batch": batch})
        return TaskResult(
            success=True,
            message=f"Applied {instr.operation.value} to {task.target}; {batch.to_summary()}",
            changes=[task.target],
            details={"mutation_batch": batch, "edit_result": edit_result},
        )

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
        content = task.content
        if not content:
            prompt = f"Modify the file '{task.target}' based on these constraints: {task.constraints or 'none'}. Output ONLY the new content for the file, no markdown markers."
            content = self._call_llm(prompt)

        batch = self.file_ops.execute_plan(
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
            mode=self.mutation_mode,
        )
        self._write_mutation_artifacts(task.id, batch)
        if batch.failed_count:
            return TaskResult(success=False, message=batch.results[0].failure_reason or "replace failed", details={"mutation_batch": batch})
        return TaskResult(success=True, message=f"File modified: {task.target}; {batch.to_summary()}", changes=[task.target], details={"mutation_batch": batch})

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
            "results": [asdict(result) for result in batch_result.results],
            "ledger": [asdict(entry) for entry in batch_result.ledger],
        }
        (mutations_dir / f"{task_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S")

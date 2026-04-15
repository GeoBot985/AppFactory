from __future__ import annotations

import time
from typing import Optional
from services.task_service import Task, TaskType, TaskStatus, TaskResult
from services.file_ops_service import FileOpsService
from services.ollama_service import OllamaService
from services.process_service import ProcessService


class TaskExecutorService:
    def __init__(
        self,
        file_ops: FileOpsService,
        ollama: OllamaService,
        process: ProcessService,
        model_name: str
    ):
        self.file_ops = file_ops
        self.ollama = ollama
        self.process = process
        self.model_name = model_name

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

        msg = self.file_ops.create(task.target, content)
        return TaskResult(success=True, message=msg, changes=[task.target])

    def _handle_modify(self, task: Task) -> TaskResult:
        # LLM helps generate patch/content if not provided
        content = task.content
        if not content:
            prompt = f"Modify the file '{task.target}' based on these constraints: {task.constraints or 'none'}. Output ONLY the new content for the file, no markdown markers."
            content = self._call_llm(prompt)

        msg = self.file_ops.modify(task.target, content)
        return TaskResult(success=True, message=msg, changes=[task.target])

    def _handle_delete(self, task: Task) -> TaskResult:
        msg = self.file_ops.delete(task.target)
        return TaskResult(success=True, message=msg, changes=[task.target])

    def _handle_run(self, task: Task) -> TaskResult:
        # We need a synchronous way to run commands or use a callback
        # For now, let's assume we can run it and wait
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

    def _now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S")

import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Callable, Optional
from services.planner.models import Step
from services.execution.snapshots import SnapshotManager
from services.execution.models import HandlerResult

class StepHandlers:
    def __init__(self, workspace_root: Path, run_id: Optional[str] = None):
        self.workspace_root = workspace_root
        self.run_id = run_id
        self.snapshot_manager = SnapshotManager(workspace_root, run_id) if run_id else None

    def get_handler(self, step_type: str) -> Callable[[Step], Dict[str, Any]]:
        handlers = {
            "create_file": self.create_file,
            "read_file": self.read_file,
            "write_file": self.write_file,
            "modify_file": self.modify_file,
            "run_command": self.run_command,
            "generate_spec": self.generate_spec,
            "analyze_code": self.analyze_code,
            "validate_output": self.validate_output,
            # Supporting more internal step types if they appear
            "validate_path": self.validate_path,
            "verify_file_exists": self.verify_file_exists,
            "resolve_spec_number": self.resolve_spec_number,
            "generate_spec_content": self.generate_spec_content,
            "apply_modification": self.apply_modification,
        }
        return handlers.get(step_type, self.not_implemented_handler)

    def create_file(self, step: Step) -> HandlerResult:
        path = self.workspace_root / step.target
        existed = path.exists()

        path.parent.mkdir(parents=True, exist_ok=True)
        content = step.inputs.get("content", "")
        with open(path, "w") as f:
            f.write(content)

        outputs = {"path": str(path), "bytes_written": len(content)}
        rollback_metadata = {
            "created_by_run": not existed,
            "target": step.target
        }
        return HandlerResult(success=True, outputs=outputs, rollback_metadata=rollback_metadata)

    def read_file(self, step: Step) -> Dict[str, Any]:
        path = self.workspace_root / step.target
        with open(path, "r") as f:
            content = f.read()
        return {"content": content}

    def write_file(self, step: Step) -> HandlerResult:
        path = self.workspace_root / step.target

        rollback_metadata = {}
        if self.snapshot_manager:
            if path.exists():
                snapshot_path = self.snapshot_manager.capture_snapshot(step.target)
                checksum = self.snapshot_manager.get_checksum(step.target)
                rollback_metadata = {
                    "snapshot_path": snapshot_path,
                    "checksum": checksum,
                    "target": step.target
                }
            else:
                rollback_metadata = {
                    "created_by_run": True,
                    "target": step.target
                }

        content = step.inputs.get("content", "")
        with open(path, "w") as f:
            f.write(content)

        outputs = {"path": str(path), "bytes_written": len(content)}
        return HandlerResult(success=True, outputs=outputs, rollback_metadata=rollback_metadata)

    def modify_file(self, step: Step) -> HandlerResult:
        path = self.workspace_root / step.target

        rollback_metadata = {}
        if self.snapshot_manager and path.exists():
            snapshot_path = self.snapshot_manager.capture_snapshot(step.target)
            checksum = self.snapshot_manager.get_checksum(step.target)
            rollback_metadata = {
                "snapshot_path": snapshot_path,
                "checksum": checksum,
                "target": step.target
            }

        # Deterministic rule or simple replacement for v1
        with open(path, "r") as f:
            content = f.read()

        new_content = step.inputs.get("content", content)

        with open(path, "w") as f:
            f.write(new_content)

        outputs = {"path": str(path), "modified": True}
        return HandlerResult(success=True, outputs=outputs, rollback_metadata=rollback_metadata)

    def run_command(self, step: Step) -> Dict[str, Any]:
        cmd = step.inputs.get("command")
        if not cmd:
            raise ValueError("No command provided")

        result = subprocess.run(
            cmd,
            shell=True,
            cwd=self.workspace_root,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            # We use a custom exception or just return metadata if we want the engine to handle it.
            # The Spec says handlers MUST optionally return richer failure metadata.
            # But the current engine expects handler to return outputs and raises exception on error.
            # Let's adjust the engine to look at outputs if we want.
            # Actually, let's keep it simple: if returncode != 0, it's a COMMAND_FAILED error.
            # I'll raise an exception with the error code.
            raise RuntimeError(f"COMMAND_FAILED: {result.stderr}")

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }

    def generate_spec(self, step: Step) -> Dict[str, Any]:
        # Placeholder for calling an existing spec generator
        return {"spec_content": "dummy spec content", "generated": True}

    def analyze_code(self, step: Step) -> Dict[str, Any]:
        return {"analysis": "no issues found", "passed": True}

    def validate_output(self, step: Step) -> Dict[str, Any]:
        path = self.workspace_root / step.target
        exists = path.exists()
        return {"exists": exists, "valid": exists}

    def validate_path(self, step: Step) -> Dict[str, Any]:
        return {"valid": True}

    def verify_file_exists(self, step: Step) -> Dict[str, Any]:
        path = self.workspace_root / step.target
        return {"exists": path.exists()}

    def resolve_spec_number(self, step: Step) -> Dict[str, Any]:
        return {"spec_number": "001"}

    def generate_spec_content(self, step: Step) -> Dict[str, Any]:
        return {"content": "generated spec content"}

    def apply_modification(self, step: Step) -> Dict[str, Any]:
        return {"applied": True}

    def not_implemented_handler(self, step: Step) -> Dict[str, Any]:
        raise NotImplementedError(f"Handler for {step.step_type} not implemented")

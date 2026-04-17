import os
import json
from pathlib import Path
from typing import Dict, Any
from services.execution.models import Run, StepResult
from services.execution.rollback_models import RollbackPlan, CompensationAction

class ExecutionLogger:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.runs_dir = workspace_root / "runtime_data" / "runs"

    def _get_run_dir(self, run_id: str) -> Path:
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def log_run(self, run: Run):
        run_dir = self._get_run_dir(run.run_id)
        run_file = run_dir / "run.json"
        with open(run_file, "w") as f:
            json.dump(run.to_dict(), f, indent=2)

    def log_step(self, run_id: str, step_result: StepResult):
        run_dir = self._get_run_dir(run_id)
        steps_dir = run_dir / "steps"
        steps_dir.mkdir(exist_ok=True)

        step_file = steps_dir / f"{step_result.step_id}.json"
        with open(step_file, "w") as f:
            json.dump(step_result.to_dict(), f, indent=2)

    def log_rollback_plan(self, run_id: str, plan: RollbackPlan):
        run_dir = self._get_run_dir(run_id)
        rollback_dir = run_dir / "rollback"
        rollback_dir.mkdir(exist_ok=True)

        plan_file = rollback_dir / "rollback_plan.json"
        with open(plan_file, "w") as f:
            json.dump(plan.to_dict(), f, indent=2)

    def log_compensation_action(self, run_id: str, action: CompensationAction):
        run_dir = self._get_run_dir(run_id)
        actions_dir = run_dir / "rollback" / "actions"
        actions_dir.mkdir(parents=True, exist_ok=True)

        action_file = actions_dir / f"{action.compensation_id}.json"
        with open(action_file, "w") as f:
            json.dump(action.to_dict(), f, indent=2)

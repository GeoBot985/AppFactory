from pathlib import Path
from services.planner.models import ExecutionPlan
from services.execution.models import Run
from services.execution.engine import ExecutionEngine

def execute_plan(plan: ExecutionPlan, workspace_root: Path) -> Run:
    engine = ExecutionEngine(workspace_root)
    return engine.execute(plan)

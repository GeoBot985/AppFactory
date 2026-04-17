from __future__ import annotations
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from services.planner.models import ExecutionPlan, Step
from services.execution.models import Run, StepResult
from services.execution.logger import ExecutionLogger
from services.execution.contracts import ContractEvaluator
from services.execution.handlers import StepHandlers

class ExecutionEngine:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.logger = ExecutionLogger(workspace_root)
        self.contracts = ContractEvaluator(workspace_root)
        self.handlers = StepHandlers(workspace_root)

    def execute(self, plan: ExecutionPlan) -> Run:
        print("RUN START")
        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run = Run(run_id=run_id, plan_id=plan.plan_id, status="running")
        self.logger.log_run(run)

        ordered_steps = self._get_ordered_steps(plan)

        failed = False
        for i, step_id in enumerate(ordered_steps):
            step = plan.steps[step_id]

            if failed:
                self._skip_step(run, step)
                continue

            if not self._dependencies_satisfied(run, step):
                self._fail_step(run, step, "DEPENDENCY_NOT_SATISFIED", "One or more dependencies failed or were skipped")
                failed = True
                continue

            result = self._execute_step(run, step)
            print(f"[{i+1}/{len(ordered_steps)}] {step.step_type} → {result.status}" + (f" ({result.error_code})" if result.status == "failed" else ""))
            if result.status == "failed":
                failed = True

        run.status = "failed" if failed else "completed"
        run.ended_at = datetime.now()
        self.logger.log_run(run)
        print(f"RUN {'FAILED' if failed else 'COMPLETED'}")
        return run

    def _get_ordered_steps(self, plan: ExecutionPlan) -> List[str]:
        # Simple topological sort or use dependency order
        visited = set()
        ordered = []

        def visit(step_id):
            if step_id in visited:
                return
            step = plan.steps[step_id]
            for dep_id in step.dependencies:
                visit(dep_id)
            visited.add(step_id)
            ordered.append(step_id)

        for step_id in plan.steps:
            visit(step_id)

        return ordered

    def _dependencies_satisfied(self, run: Run, step: Step) -> bool:
        for dep_id in step.dependencies:
            dep_result = run.step_results.get(dep_id)
            if not dep_result or dep_result.status != "completed":
                return False
        return True

    def _execute_step(self, run: Run, step: Step) -> StepResult:
        run.current_step_id = step.step_id
        result = StepResult(step_id=step.step_id, status="running", started_at=datetime.now(), inputs=step.inputs)
        run.step_results[step.step_id] = result
        self.logger.log_step(run.run_id, result)

        # 1. Preconditions
        if not self.contracts.evaluate_preconditions(step):
            return self._fail_step(run, step, "PRECONDITION_FAILED", "Preconditions not met")

        result.preconditions_passed = True

        # 2. Handler
        try:
            handler = self.handlers.get_handler(step.step_type)
            outputs = handler(step)
            result.outputs = outputs
        except Exception as e:
            return self._fail_step(run, step, "EXECUTION_ERROR", str(e))

        # 3. Postconditions
        if not self.contracts.evaluate_postconditions(step, result.outputs):
            return self._fail_step(run, step, "POSTCONDITION_FAILED", "Postconditions not met")

        result.postconditions_passed = True
        result.status = "completed"
        result.ended_at = datetime.now()
        self.logger.log_step(run.run_id, result)
        return result

    def _fail_step(self, run: Run, step: Step, error_code: str, error_message: str) -> StepResult:
        result = run.step_results.get(step.step_id)
        if not result:
            result = StepResult(step_id=step.step_id, inputs=step.inputs)
            run.step_results[step.step_id] = result

        result.status = "failed"
        result.error_code = error_code
        result.error_message = error_message
        result.ended_at = datetime.now()
        self.logger.log_step(run.run_id, result)
        return result

    def _skip_step(self, run: Run, step: Step):
        result = StepResult(step_id=step.step_id, status="skipped", inputs=step.inputs)
        run.step_results[step.step_id] = result
        self.logger.log_step(run.run_id, result)

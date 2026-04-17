import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from services.input_compiler.models import CompiledSpecIR, OperationIR, ConstraintIR, CompileStatus, OperationType
from services.planner.models import ExecutionPlan, Step, StepContract, PlanIssue
from services.execution.models import Run, StepResult, StepAttempt
from services.execution.rollback_models import RollbackPlan, CompensationAction

class ReplayArtifactLoader:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.compiler_runs_dir = workspace_root / "runtime_data" / "compiler_runs"
        self.execution_plans_dir = workspace_root / "runtime_data" / "execution_plans"
        self.runs_dir = workspace_root / "runtime_data" / "runs"

    def load_run_artifacts(self, run_id: str) -> Dict[str, Any]:
        run_dir = self.runs_dir / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory not found: {run_dir}")

        run_file = run_dir / "run.json"
        if not run_file.exists():
            raise FileNotFoundError(f"run.json not found in {run_dir}")

        with open(run_file, "r") as f:
            run_data = json.load(f)

        run = self._parse_run(run_data)

        # Load step results
        steps_dir = run_dir / "steps"
        if steps_dir.exists():
            for step_file in steps_dir.glob("*.json"):
                with open(step_file, "r") as f:
                    step_data = json.load(f)
                    step_result = self._parse_step_result(step_data)
                    run.step_results[step_result.step_id] = step_result

        # Load plan
        plan_id = run.plan_id
        plan = self.load_execution_plan(plan_id)

        # Load IR
        ir_ref = plan.ir_ref
        ir = self.load_compiled_ir(ir_ref)

        # Load rollback plan if exists
        rollback_plan = None
        rollback_dir = run_dir / "rollback"
        if rollback_dir.exists():
            rollback_plan_file = rollback_dir / "rollback_plan.json"
            if rollback_plan_file.exists():
                with open(rollback_plan_file, "r") as f:
                    rb_data = json.load(f)
                    rollback_plan = self._parse_rollback_plan(rb_data)

                    # Load compensation actions
                    actions_dir = rollback_dir / "actions"
                    if actions_dir.exists():
                        for action_file in actions_dir.glob("*.json"):
                            with open(action_file, "r") as f:
                                action_data = json.load(f)
                                action = self._parse_compensation_action(action_data)
                                rollback_plan.actions.append(action)

        return {
            "run": run,
            "plan": plan,
            "ir": ir,
            "rollback_plan": rollback_plan
        }

    def load_execution_plan(self, plan_id: str) -> ExecutionPlan:
        plan_file = self.execution_plans_dir / f"{plan_id}.json"
        if not plan_file.exists():
            raise FileNotFoundError(f"Execution plan not found: {plan_file}")

        with open(plan_file, "r") as f:
            data = json.load(f)

        steps = {}
        for sid, sdata in data.get("steps", {}).items():
            contract_data = sdata.get("contract", {})
            contract = StepContract(
                preconditions=contract_data.get("preconditions", []),
                postconditions=contract_data.get("postconditions", []),
                failure_modes=contract_data.get("failure_modes", []),
                compensation_type=contract_data.get("compensation_type", "non_reversible"),
                compensation_template=contract_data.get("compensation_template")
            )
            steps[sid] = Step(
                step_id=sid,
                step_type=sdata.get("step_type"),
                target=sdata.get("target"),
                inputs=sdata.get("inputs", {}),
                outputs=sdata.get("outputs", {}),
                dependencies=sdata.get("dependencies", []),
                contract=contract,
                operation_id=sdata.get("operation_id")
            )

        issues = [PlanIssue(i["code"], i["message"], i["severity"]) for i in data.get("issues", [])]

        return ExecutionPlan(
            plan_id=data["plan_id"],
            ir_ref=data["ir_ref"],
            steps=steps,
            root_steps=data.get("root_steps", []),
            terminal_steps=data.get("terminal_steps", []),
            status=data.get("status", "invalid"),
            issues=issues,
            created_at=data.get("created_at", "")
        )

    def load_compiled_ir(self, ir_ref: str) -> CompiledSpecIR:
        ir_file = self.compiler_runs_dir / f"{ir_ref}.json"
        if not ir_file.exists():
            raise FileNotFoundError(f"Compiled IR not found: {ir_file}")

        with open(ir_file, "r") as f:
            data = json.load(f)

        operations = [
            OperationIR(
                op_type=OperationType(op["op_type"]),
                target=op.get("target"),
                instruction=op.get("instruction", ""),
                depends_on=op.get("depends_on", [])
            ) for op in data.get("operations", [])
        ]

        constraints = [
            ConstraintIR(c["constraint_type"], c["value"])
            for c in data.get("constraints", [])
        ]

        return CompiledSpecIR(
            request_id=data["request_id"],
            title=data.get("title", ""),
            objective=data.get("objective", ""),
            target_path=data.get("target_path"),
            operations=operations,
            constraints=constraints,
            defaults_applied=data.get("defaults_applied", []),
            assumptions=data.get("assumptions", []),
            open_questions=data.get("open_questions", []),
            warnings=data.get("warnings", []),
            errors=data.get("errors", []),
            compile_status=CompileStatus(data.get("compile_status", "blocked")),
            original_text=data.get("original_text", ""),
            normalized_text=data.get("normalized_text", ""),
            timestamp=data.get("timestamp", "")
        )

    def _parse_run(self, data: Dict[str, Any]) -> Run:
        run = Run(
            run_id=data["run_id"],
            plan_id=data["plan_id"],
            status=data.get("status", "pending"),
            current_step_id=data.get("current_step_id"),
            started_at=datetime.fromisoformat(data["started_at"]),
            ended_at=datetime.fromisoformat(data["ended_at"]) if data.get("ended_at") else None,
            total_retries=data.get("total_retries", 0),
            recovered_steps=data.get("recovered_steps", 0),
            retry_exhausted_steps=data.get("retry_exhausted_steps", 0),
            rollback_status=data.get("rollback_status", "not_needed"),
            consistency_outcome=data.get("consistency_outcome", "clean")
        )
        return run

    def _parse_step_result(self, data: Dict[str, Any]) -> StepResult:
        attempts = []
        for adata in data.get("attempts", []):
            attempts.append(StepAttempt(
                attempt_index=adata["attempt_index"],
                started_at=datetime.fromisoformat(adata["started_at"]),
                ended_at=datetime.fromisoformat(adata["ended_at"]) if adata.get("ended_at") else None,
                status=adata.get("status", "running"),
                error_code=adata.get("error_code"),
                error_message=adata.get("error_message"),
                preconditions_passed=adata.get("preconditions_passed", False),
                postconditions_passed=adata.get("postconditions_passed", False),
                outputs=adata.get("outputs", {}),
                rollback_metadata=adata.get("rollback_metadata", {})
            ))

        return StepResult(
            step_id=data["step_id"],
            status=data.get("status", "pending"),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            ended_at=datetime.fromisoformat(data["ended_at"]) if data.get("ended_at") else None,
            inputs=data.get("inputs", {}),
            outputs=data.get("outputs", {}),
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
            preconditions_passed=data.get("preconditions_passed", False),
            postconditions_passed=data.get("postconditions_passed", False),
            attempts=attempts,
            final_attempt_count=data.get("final_attempt_count", 0),
            recovered_via_retry=data.get("recovered_via_retry", False),
            retry_exhausted=data.get("retry_exhausted", False),
            rollback_metadata=data.get("rollback_metadata", {})
        )

    def _parse_rollback_plan(self, data: Dict[str, Any]) -> RollbackPlan:
        return RollbackPlan(
            plan_id=data["plan_id"],
            run_id=data["run_id"],
            status=data.get("status", "pending"),
            actions=[]
        )

    def _parse_compensation_action(self, data: Dict[str, Any]) -> CompensationAction:
        return CompensationAction(
            compensation_id=data["compensation_id"],
            source_step_id=data["source_step_id"],
            action_type=data["action_type"],
            parameters=data.get("parameters", {}),
            status=data.get("status", "pending"),
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            ended_at=datetime.fromisoformat(data["ended_at"]) if data.get("ended_at") else None
        )

from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from services.input_compiler.models import CompiledSpecIR, OperationIR
from services.planner.models import ExecutionPlan, Step, StepContract, PlanIssue
from services.planner.step_templates import get_template
from services.planner.dependency_resolver import DependencyResolver
from services.planner.plan_validator import PlanValidator

class PlanBuilder:
    def __init__(self):
        self.resolver = DependencyResolver()
        self.validator = PlanValidator()

    def build_plan(self, ir: CompiledSpecIR) -> ExecutionPlan:
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        plan = ExecutionPlan(
            plan_id=plan_id,
            ir_ref=ir.request_id,
            created_at=datetime.now().isoformat()
        )

        all_steps: List[Step] = []
        op_dependencies: Dict[str, List[str]] = {}

        # Map original operation index/ID to our internal op_id
        # IR operations are sequential, but might have explicit depends_on
        # OperationIR doesn't have an 'id' field, so we use their index.

        # 1. Operation -> Step Expansion
        for i, op in enumerate(ir.operations):
            op_id = f"op_{i}"
            steps = self._expand_operation(op, op_id)
            all_steps.extend(steps)

            # IR depends_on uses targets or some IDs?
            # OperationIR.depends_on is List[str].
            # Let's assume they refer to other op targets or indices.
            # Spec says "if operation B depends on output of A: explicit dependency required (from IR or inferred)"
            # For now, let's just use what's in op.depends_on if it matches any prior op target.

            deps = []
            for dep_ref in op.depends_on:
                # Find previous op with this target or index
                for prev_i, prev_op in enumerate(ir.operations[:i]):
                    if prev_op.target == dep_ref or str(prev_i) == dep_ref:
                        deps.append(f"op_{prev_i}")

            if deps:
                op_dependencies[op_id] = deps

        # 2. Dependency Resolution
        all_steps = self.resolver.resolve(all_steps, op_dependencies)

        # Populate plan.steps dict
        for step in all_steps:
            plan.steps[step.step_id] = step

        # 3. Identify Root and Terminal steps
        plan.root_steps = self.resolver.get_root_steps(plan.steps)
        plan.terminal_steps = self.resolver.get_terminal_steps(plan.steps)

        # 4. Validation
        issues = self.validator.validate(plan)
        plan.issues = issues

        if any(issue.severity == "error" for issue in issues):
            plan.status = "invalid"
        else:
            plan.status = "ready"

        return plan

    def _expand_operation(self, op: OperationIR, op_id: str) -> List[Step]:
        template = get_template(op.op_type.value)
        steps = []

        for i, step_def in enumerate(template):
            step_id = f"{op_id}_s{i}"
            contract_def = step_def.get("contract", {})
            contract = StepContract(
                preconditions=contract_def.get("preconditions", []),
                postconditions=contract_def.get("postconditions", []),
                failure_modes=contract_def.get("failure_modes", [])
            )

            step = Step(
                step_id=step_id,
                step_type=step_def["step_type"],
                target=op.target,
                inputs={"instruction": op.instruction},
                contract=contract,
                operation_id=op_id
            )
            steps.append(step)

        return steps

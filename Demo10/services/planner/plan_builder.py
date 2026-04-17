from __future__ import annotations
import uuid
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from services.input_compiler.models import CompiledSpecIR, OperationIR
from services.planner.models import ExecutionPlan, Step, StepContract, PlanIssue
from services.planner.step_templates import get_template
from Demo10.macros.library import MacroLibraryManager
from Demo10.macros.expansion import MacroExpansionEngine
from Demo10.routing.engine import RoutingEngine
from Demo10.telemetry.events import TelemetryEmitter
from Demo10.telemetry.models import TelemetryEventType
from services.planner.dependency_resolver import DependencyResolver
from services.planner.plan_validator import PlanValidator

class PlanBuilder:
    def __init__(self, workspace_root: Optional[Path] = None):
        self.resolver = DependencyResolver()
        self.validator = PlanValidator()
        self.workspace_root = workspace_root or Path(".")
        self.macro_library = MacroLibraryManager(self.workspace_root)
        self.macro_expander = MacroExpansionEngine(self.macro_library)
        self.routing_engine = RoutingEngine(self.workspace_root)
        self.telemetry = TelemetryEmitter(self.workspace_root)

    def build_plan(self, ir: CompiledSpecIR) -> ExecutionPlan:
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        plan = ExecutionPlan(
            plan_id=plan_id,
            ir_ref=ir.request_id,
            created_at=datetime.now().isoformat()
        )

        all_steps: List[Step] = []
        op_dependencies: Dict[str, List[str]] = {}

        # 0. Routing to Macros
        self.telemetry.emit("routing_started", {"request_id": ir.request_id})
        decision = self.routing_engine.route_to_macros(ir)

        if not decision.fallback_used:
            self.telemetry.emit("routing_selected", decision.to_dict())

            macro_steps = []
            expansion_failed = False

            for m_idx, macro_id in enumerate(decision.selected_macros):
                macro_obj = self.routing_engine.get_macro_by_id(macro_id)
                if not macro_obj:
                    expansion_failed = True
                    break

                inputs = self.routing_engine.binder.bind_inputs(macro_obj, ir)
                res = self.macro_expander.expand_macro(macro_id, inputs)

                if res.status == "expanded":
                    for s_idx, step_def in enumerate(res.expanded_steps):
                        step_id = f"m{m_idx}_{s_idx}"
                        contract_def = step_def.get("contract", {})
                        contract = StepContract(
                            preconditions=contract_def.get("preconditions", []),
                            postconditions=contract_def.get("postconditions", []),
                            failure_modes=contract_def.get("failure_modes", [])
                        )
                        step = Step(
                            step_id=step_id,
                            step_type=step_def["step_type"],
                            target=step_def.get("target"),
                            inputs=step_def.get("inputs", {}),
                            contract=contract
                        )
                        macro_steps.append(step)
                else:
                    self.telemetry.emit("routing_failed", {"reason": "expansion_failed", "macro_id": macro_id, "issues": res.issues})
                    expansion_failed = True
                    break

            if not expansion_failed:
                all_steps.extend(macro_steps)
            else:
                decision.fallback_used = True

        if decision.fallback_used:
            self.telemetry.emit("routing_fallback", {"reasons": decision.reasons})
            # 1. Operation -> Step Expansion (Raw)
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
        # Macro selection logic: check if there's an active macro matching the operation type
        active_macro = self.macro_library.get_active_macro(op.op_type.value)

        if active_macro:
            # Expand macro
            bound_inputs = {"instruction": op.instruction, "target": op.target}
            res = self.macro_expander.expand_macro(active_macro.macro_id, bound_inputs)
            if res.status == "expanded":
                steps = []
                for i, step_def in enumerate(res.expanded_steps):
                    step_id = f"{op_id}_m_{i}"
                    contract_def = step_def.get("contract", {})
                    contract = StepContract(
                        preconditions=contract_def.get("preconditions", []),
                        postconditions=contract_def.get("postconditions", []),
                        failure_modes=contract_def.get("failure_modes", [])
                    )
                    step = Step(
                        step_id=step_id,
                        step_type=step_def["step_type"],
                        target=step_def.get("target", op.target),
                        inputs=step_def.get("inputs", {}),
                        contract=contract,
                        operation_id=op_id
                    )
                    steps.append(step)
                return steps

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

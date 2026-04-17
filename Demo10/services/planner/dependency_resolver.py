from __future__ import annotations
from typing import List, Dict, Any, Set
from services.planner.models import Step

class DependencyResolver:
    def resolve(self, steps: List[Step], op_dependencies: Dict[str, List[str]] = None) -> List[Step]:
        # 1. Intra-operation dependencies (sequential within op)
        # 2. Inter-operation dependencies (based on IR depends_on and file target overlap)

        # Link sequential steps within the same operation
        last_step_by_op: Dict[str, str] = {}
        op_first_step: Dict[str, str] = {}
        op_last_step: Dict[str, str] = {}

        for step in steps:
            if step.operation_id:
                if step.operation_id not in op_first_step:
                    op_first_step[step.operation_id] = step.step_id

                if step.operation_id in last_step_by_op:
                    prev_id = last_step_by_op[step.operation_id]
                    if prev_id not in step.dependencies:
                        step.dependencies.append(prev_id)
                last_step_by_op[step.operation_id] = step.step_id
                op_last_step[step.operation_id] = step.step_id

        # Inter-operation dependencies: Explicit (from op_dependencies)
        if op_dependencies:
            for op_id, deps in op_dependencies.items():
                if op_id in op_first_step:
                    first_step_id = op_first_step[op_id]
                    for dep_op_id in deps:
                        if dep_op_id in op_last_step:
                            last_step_of_dep = op_last_step[dep_op_id]
                            # Find the first step object and add dependency
                            for s in steps:
                                if s.step_id == first_step_id:
                                    if last_step_of_dep not in s.dependencies:
                                        s.dependencies.append(last_step_of_dep)
                                    break

        # Inter-operation dependencies: same file target
        last_step_by_target: Dict[str, str] = {}

        # Track targets per operation
        op_targets: Dict[str, str] = {}
        for step in steps:
            if step.operation_id and step.target:
                op_targets[step.operation_id] = step.target

        # Enforce ordering for same-file targets
        processed_ops: List[str] = []
        op_order: Dict[str, int] = {}

        curr_idx = 0
        for step in steps:
            if step.operation_id and step.operation_id not in op_order:
                op_order[step.operation_id] = curr_idx
                curr_idx += 1
                processed_ops.append(step.operation_id)

        for i, op_id in enumerate(processed_ops):
            target = op_targets.get(op_id)
            if not target:
                continue

            # Find previous operations targeting same file
            for prev_op_id in processed_ops[:i]:
                if op_targets.get(prev_op_id) == target:
                    # Current op's first step depends on previous op's last step
                    first_step_id = op_first_step[op_id]
                    last_step_of_prev = op_last_step[prev_op_id]

                    # Find the first step object
                    for s in steps:
                        if s.step_id == first_step_id:
                            if last_step_of_prev not in s.dependencies:
                                s.dependencies.append(last_step_of_prev)
                            break

        return steps

    def get_root_steps(self, steps: Dict[str, Step]) -> List[str]:
        roots = []
        for sid, step in steps.items():
            if not step.dependencies:
                roots.append(sid)
        return roots

    def get_terminal_steps(self, steps: Dict[str, Step]) -> List[str]:
        depended_on = set()
        for step in steps.values():
            for dep in step.dependencies:
                depended_on.add(dep)

        terminals = []
        for sid in steps:
            if sid not in depended_on:
                terminals.append(sid)
        return terminals

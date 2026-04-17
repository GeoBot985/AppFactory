from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Literal

@dataclass
class StepContract:
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    failure_modes: List[str] = field(default_factory=list)
    compensation_type: str = "non_reversible" # CompensationType literal
    compensation_template: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "preconditions": self.preconditions,
            "postconditions": self.postconditions,
            "failure_modes": self.failure_modes,
            "compensation_type": self.compensation_type,
            "compensation_template": self.compensation_template
        }

@dataclass
class Step:
    step_id: str
    step_type: Literal[
        "read_file",
        "write_file",
        "modify_file",
        "create_file",
        "run_command",
        "analyze_code",
        "generate_spec",
        "validate_output",
        "validate_path",
        "verify_file_exists",
        "verify_changes",
        "resolve_spec_number",
        "generate_spec_content",
        "apply_modification"
    ]
    target: Optional[str] = None
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    contract: StepContract = field(default_factory=StepContract)
    operation_id: Optional[str] = None # Link back to OperationIR index or ID

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_type": self.step_type,
            "target": self.target,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "dependencies": self.dependencies,
            "contract": self.contract.to_dict(),
            "operation_id": self.operation_id
        }

@dataclass
class PlanIssue:
    code: str
    message: str
    severity: Literal["error", "warning"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity
        }

@dataclass
class ExecutionPlan:
    plan_id: str
    ir_ref: str
    steps: Dict[str, Step] = field(default_factory=dict)
    root_steps: List[str] = field(default_factory=list)
    terminal_steps: List[str] = field(default_factory=list)
    status: Literal["ready", "invalid"] = "invalid"
    issues: List[PlanIssue] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "ir_ref": self.ir_ref,
            "steps": {k: v.to_dict() for k, v in self.steps.items()},
            "root_steps": self.root_steps,
            "terminal_steps": self.terminal_steps,
            "status": self.status,
            "issues": [i.to_dict() for i in self.issues],
            "created_at": self.created_at
        }

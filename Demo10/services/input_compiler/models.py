from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Literal
from enum import Enum

class CompileStatus(Enum):
    COMPILED_CLEAN = "compiled_clean"
    COMPILED_WITH_WARNINGS = "compiled_with_warnings"
    BLOCKED = "blocked"

class OperationType(Enum):
    CREATE_FILE = "create_file"
    MODIFY_FILE = "modify_file"
    RUN_COMMAND = "run_command"
    ANALYZE_CODEBASE = "analyze_codebase"
    WRITE_SPEC = "write_spec"
    REVIEW_OUTPUT = "review_output"
    SEARCH_CODE = "search_code"

@dataclass
class OperationIR:
    op_type: OperationType
    target: Optional[str]
    instruction: str
    depends_on: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "op_type": self.op_type.value,
            "target": self.target,
            "instruction": self.instruction,
            "depends_on": self.depends_on
        }

@dataclass
class ConstraintIR:
    constraint_type: str
    value: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "constraint_type": self.constraint_type,
            "value": self.value
        }

@dataclass
class CompiledSpecIR:
    request_id: str
    title: str
    objective: str
    target_path: Optional[str] = None
    operations: List[OperationIR] = field(default_factory=list)
    constraints: List[ConstraintIR] = field(default_factory=list)
    defaults_applied: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    compile_status: CompileStatus = CompileStatus.BLOCKED

    # Metadata for persistence
    original_text: str = ""
    normalized_text: str = ""
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "title": self.title,
            "objective": self.objective,
            "target_path": self.target_path,
            "operations": [op.to_dict() for op in self.operations],
            "constraints": [c.to_dict() for c in self.constraints],
            "defaults_applied": self.defaults_applied,
            "assumptions": self.assumptions,
            "open_questions": self.open_questions,
            "warnings": self.warnings,
            "errors": self.errors,
            "compile_status": self.compile_status.value,
            "original_text": self.original_text,
            "normalized_text": self.normalized_text,
            "timestamp": self.timestamp
        }

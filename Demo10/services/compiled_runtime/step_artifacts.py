from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class StepArtifactBundle:
    run_id: str
    task_id: str
    task_type: str
    status: str
    input_summary: str = ""
    output_summary: str = ""
    artifacts: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    attempt_history_refs: List[str] = field(default_factory=list)
    mutation_refs: List[str] = field(default_factory=list)
    test_refs: List[str] = field(default_factory=list)
    validation_refs: List[str] = field(default_factory=list)
    metrics: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "artifacts": self.artifacts,
            "warnings": self.warnings,
            "errors": self.errors,
            "attempt_history_refs": self.attempt_history_refs,
            "mutation_refs": self.mutation_refs,
            "test_refs": self.test_refs,
            "validation_refs": self.validation_refs,
            "metrics": self.metrics,
            "started_at": self.started_at,
            "completed_at": self.completed_at
        }

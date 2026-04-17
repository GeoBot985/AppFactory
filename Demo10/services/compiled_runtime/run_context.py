from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from services.context.context_package import GenerationContextPackage
from services.targeting.models import ScopeContract
from services.file_ops.models import FileOperationBatchResult

@dataclass
class SharedRunContext:
    """Shared state passed between tasks in a CompiledPlanRun."""
    selected_context: Optional[GenerationContextPackage] = None
    scope_contract: Optional[ScopeContract] = None
    candidate_file_ops: List[Any] = field(default_factory=list) # List[FileOperation]
    validated_file_ops: List[Any] = field(default_factory=list)
    mutation_previews: Dict[str, str] = field(default_factory=dict) # path -> diff
    last_mutation_batch: Optional[FileOperationBatchResult] = None
    current_changeset: Optional[Any] = None # services.apply.models.ChangeSet
    last_transaction: Optional[Any] = None # services.apply.models.ApplyTransaction
    test_results: Dict[str, Any] = field(default_factory=dict)
    validation_results: Dict[str, Any] = field(default_factory=dict)

    # Store any other task-produced artifacts by key
    artifacts: Dict[str, Any] = field(default_factory=dict)

    def get_artifact(self, key: str) -> Any:
        return self.artifacts.get(key)

    def set_artifact(self, key: str, value: Any):
        self.artifacts[key] = value

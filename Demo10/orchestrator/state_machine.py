from typing import Dict, List, Set, Optional
from .stages import OrchestratorStage

class StateMachine:
    def __init__(self):
        self.transitions: Dict[OrchestratorStage, Set[OrchestratorStage]] = {
            OrchestratorStage.REQUEST_RECEIVED: {OrchestratorStage.NORMALIZATION, OrchestratorStage.FAILED},
            OrchestratorStage.NORMALIZATION: {OrchestratorStage.INTENT_DECOMPOSITION, OrchestratorStage.FAILED},
            OrchestratorStage.INTENT_DECOMPOSITION: {OrchestratorStage.PLANNING_SKELETON, OrchestratorStage.FAILED},
            OrchestratorStage.PLANNING_SKELETON: {OrchestratorStage.CLARIFICATION_GATE, OrchestratorStage.FAILED},
            OrchestratorStage.CLARIFICATION_GATE: {OrchestratorStage.DRAFT_SPEC_GENERATION, OrchestratorStage.AWAITING_USER, OrchestratorStage.BLOCKED, OrchestratorStage.FAILED},
            OrchestratorStage.AWAITING_USER: {OrchestratorStage.PLANNING_SKELETON, OrchestratorStage.DRAFT_SPEC_GENERATION, OrchestratorStage.EXECUTION, OrchestratorStage.FAILED},
            OrchestratorStage.DRAFT_SPEC_GENERATION: {OrchestratorStage.COMPILE, OrchestratorStage.FAILED},
            OrchestratorStage.COMPILE: {OrchestratorStage.PREVIEW_SIMULATION, OrchestratorStage.COMPILE_REPAIR, OrchestratorStage.FAILED},
            OrchestratorStage.COMPILE_REPAIR: {OrchestratorStage.COMPILE, OrchestratorStage.FAILED},
            OrchestratorStage.PREVIEW_SIMULATION: {OrchestratorStage.APPROVAL_GATE, OrchestratorStage.FAILED},
            OrchestratorStage.APPROVAL_GATE: {OrchestratorStage.EXECUTION, OrchestratorStage.AWAITING_USER, OrchestratorStage.BLOCKED, OrchestratorStage.FAILED},
            OrchestratorStage.EXECUTION: {OrchestratorStage.APPLY_CHANGESET, OrchestratorStage.FAILED},
            OrchestratorStage.APPLY_CHANGESET: {OrchestratorStage.POST_APPLY_VERIFICATION, OrchestratorStage.FAILED},
            OrchestratorStage.POST_APPLY_VERIFICATION: {OrchestratorStage.METRICS_AGGREGATION, OrchestratorStage.FAILED},
            OrchestratorStage.METRICS_AGGREGATION: {OrchestratorStage.COMPLETED, OrchestratorStage.FAILED},
        }

    def can_transition(self, from_stage: OrchestratorStage, to_stage: OrchestratorStage) -> bool:
        if to_stage in [OrchestratorStage.FAILED, OrchestratorStage.BLOCKED]:
            return True
        allowed = self.transitions.get(from_stage, set())
        return to_stage in allowed

    def get_next_normal_stage(self, current_stage: OrchestratorStage) -> Optional[OrchestratorStage]:
        pipeline = [
            OrchestratorStage.REQUEST_RECEIVED,
            OrchestratorStage.NORMALIZATION,
            OrchestratorStage.INTENT_DECOMPOSITION,
            OrchestratorStage.PLANNING_SKELETON,
            OrchestratorStage.CLARIFICATION_GATE,
            OrchestratorStage.DRAFT_SPEC_GENERATION,
            OrchestratorStage.COMPILE,
            OrchestratorStage.PREVIEW_SIMULATION,
            OrchestratorStage.APPROVAL_GATE,
            OrchestratorStage.EXECUTION,
            OrchestratorStage.APPLY_CHANGESET,
            OrchestratorStage.POST_APPLY_VERIFICATION,
            OrchestratorStage.METRICS_AGGREGATION,
            OrchestratorStage.COMPLETED
        ]
        try:
            idx = pipeline.index(current_stage)
            if idx + 1 < len(pipeline):
                return pipeline[idx + 1]
        except ValueError:
            pass
        return None

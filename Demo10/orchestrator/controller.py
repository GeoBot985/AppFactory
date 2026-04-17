from __future__ import annotations
import uuid
import time
import logging
from typing import Optional, Dict, Any, List

from .run_model import OrchestratorRun, StageState, StageStatus
from .stages import OrchestratorStage
from .state_machine import StateMachine

class OrchestratorController:
    def __init__(self, services: Dict[str, Any]):
        self.services = services
        self.state_machine = StateMachine()
        self.logger = logging.getLogger("Orchestrator")

    def create_run(self, request_text: str) -> OrchestratorRun:
        run_id = f"orch_{uuid.uuid4().hex[:8]}"
        run = OrchestratorRun(orchestrator_run_id=run_id, request_text=request_text)

        # Initialize all stages in PENDING
        for stage in OrchestratorStage:
            run.stages[stage.value] = StageState(stage_name=stage.value)

        # Start the first stage
        run.stages[run.current_stage].mark_running()
        return run

    def advance_stage(self, run: OrchestratorRun, to_stage: OrchestratorStage, outputs: Optional[Dict[str, Any]] = None):
        current_stage_enum = OrchestratorStage(run.current_stage)

        if not self.state_machine.can_transition(current_stage_enum, to_stage):
            raise RuntimeError(f"Invalid transition from {run.current_stage} to {to_stage.value}")

        # Mark current stage completed
        current_state = run.stages[run.current_stage]
        if current_state.status == StageStatus.RUNNING:
            current_state.mark_completed(outputs)

        # Transition
        run.current_stage = to_stage.value
        new_state = run.stages[to_stage.value]

        # Invariants: no skipping stages
        if new_state.status != StageStatus.PENDING and to_stage not in [OrchestratorStage.COMPILE, OrchestratorStage.PLANNING_SKELETON]:
             # Allow some stages to be re-run (repair loop)
             pass

        new_state.mark_running()

        self.logger.info(f"Transition: {current_stage_enum.value} -> {to_stage.value}")

    def handle_stage_failure(self, run: OrchestratorRun, error: str):
        current_state = run.stages[run.current_stage]
        current_state.mark_failed(error)
        run.current_stage = OrchestratorStage.FAILED.value
        self.logger.error(f"Stage {current_state.stage_name} failed: {error}")

    def block_run(self, run: OrchestratorRun, reason: str):
        current_state = run.stages[run.current_stage]
        current_state.mark_blocked(reason)
        run.current_stage = OrchestratorStage.BLOCKED.value
        self.logger.warning(f"Run blocked at {run.current_stage}: {reason}")

    def await_user(self, run: OrchestratorRun):
        current_state = run.stages[run.current_stage]
        current_state.mark_awaiting_user()
        run.current_stage = OrchestratorStage.AWAITING_USER.value
        self.logger.info(f"Run awaiting user input at {current_state.stage_name}")

    def resume_run(self, run: OrchestratorRun, from_stage: OrchestratorStage):
        # When resuming, we usually go back to a stage like PLANNING_SKELETON or DRAFT_SPEC_GENERATION
        # after user has provided info or approval.
        self.logger.info(f"Resuming run {run.orchestrator_run_id} from {from_stage.value}")
        run.current_stage = from_stage.value
        run.stages[from_stage.value].mark_running()

    def run_orchestrator(self, run: OrchestratorRun, stop_requested_func=None):
        """Authoritative execution loop for a run."""
        while run.current_stage != OrchestratorStage.COMPLETED.value:
            if stop_requested_func and stop_requested_func():
                self.block_run(run, "Stop requested by user")
                break

            current_stage_enum = OrchestratorStage(run.current_stage)
            next_stage = self.state_machine.get_next_normal_stage(current_stage_enum)

            if not next_stage:
                break

            try:
                # Execution logic for each stage
                result = self.execute_stage(run, next_stage)

                if result == "AWAITING_USER":
                    self.await_user(run)
                    break
                elif result == "BLOCKED":
                    self.block_run(run, "Stage blocked by gating logic")
                    break

                self.advance_stage(run, next_stage, outputs=result if isinstance(result, dict) else None)

            except Exception as e:
                self.handle_stage_failure(run, str(e))
                break

    def execute_stage(self, run: OrchestratorRun, stage: OrchestratorStage) -> Any:
        """Dispatches stage execution to appropriate services."""
        if stage == OrchestratorStage.NORMALIZATION:
            normalizer = self.services["normalizer"]
            res = normalizer.normalize(self.services.get("model", "default"), run.request_text)
            run.normalized_request_id = res.request_id
            return {"normalized": res}

        elif stage == OrchestratorStage.INTENT_DECOMPOSITION:
            return {} # Integrated into normalization/skeleton for now

        elif stage == OrchestratorStage.PLANNING_SKELETON:
            builder = self.services["skeleton_builder"]
            normalized = run.stages[OrchestratorStage.NORMALIZATION.value].outputs.get("normalized")
            if not normalized: return "BLOCKED"
            skeleton = builder.build(normalized)
            run.planning_skeleton_id = skeleton.skeleton_id
            return {"skeleton": skeleton}

        elif stage == OrchestratorStage.CLARIFICATION_GATE:
            clarification = self.services["clarification"]
            normalized = run.stages[OrchestratorStage.NORMALIZATION.value].outputs.get("normalized")
            skeleton = run.stages[OrchestratorStage.PLANNING_SKELETON.value].outputs.get("skeleton")
            if not normalized or not skeleton: return "BLOCKED"
            session = clarification.create_session(normalized, skeleton)
            run.clarification_session_id = session.session_id
            if session.status.value == "awaiting_user":
                return "AWAITING_USER"
            return {"session": session}

        elif stage == OrchestratorStage.DRAFT_SPEC_GENERATION:
            translator = self.services["translator"]
            model = self.services.get("model", "default")
            skeleton = run.stages[OrchestratorStage.PLANNING_SKELETON.value].outputs.get("skeleton")
            normalized = run.stages[OrchestratorStage.NORMALIZATION.value].outputs.get("normalized")
            draft = translator.translate_request_to_draft_spec(model, run.request_text, planning_skeleton=skeleton, normalized_request=normalized)
            run.draft_spec_id = draft.draft_id
            return {"draft": draft}

        elif stage == OrchestratorStage.COMPILE:
            compiler = self.services["compiler"]
            draft = run.stages[OrchestratorStage.DRAFT_SPEC_GENERATION.value].outputs.get("draft")
            if not draft: return "BLOCKED"
            plan, report, _, _ = compiler.compile_with_repair(draft)
            run.compiled_plan_id = plan.plan_id
            return {"plan": plan, "report": report}

        elif stage == OrchestratorStage.PREVIEW_SIMULATION:
            plan = run.stages[OrchestratorStage.COMPILE.value].outputs.get("plan")
            if not plan: return "BLOCKED"
            # Simulator usually needs an executor
            return {}

        elif stage == OrchestratorStage.APPROVAL_GATE:
            return {}

        elif stage == OrchestratorStage.EXECUTION:
            return {}

        elif stage == OrchestratorStage.APPLY_CHANGESET:
            return {}

        elif stage == OrchestratorStage.METRICS_AGGREGATION:
            return {}

        return {}

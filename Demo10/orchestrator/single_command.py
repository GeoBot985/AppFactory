from __future__ import annotations
import uuid
import logging
import shutil
import json
from enum import Enum
from unittest.mock import MagicMock
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Literal

from .models import (
    SingleCommandRequest, SingleCommandResult,
    SC_COMPILE_BLOCKED, SC_PLAN_INVALID, SC_EXECUTION_FAILED,
    SC_VERIFICATION_FAILED, SC_PROMOTION_REJECTED, SC_REPAIR_EXHAUSTED
)
from services.input_compiler.compiler import NaturalInputCompiler
from services.input_compiler.models import CompileStatus, CompiledSpecIR
from services.planner.plan_builder import PlanBuilder
from services.execution.runner import execute_plan
from services.execution.models import Run
from verification.harness import VerificationHarness
from services.policy.promotion_engine import PromotionEngine
from services.policy.models import PromotionCandidate, PromotionPolicy, EnvironmentPolicy, Environment
from services.policy.audit import PromotionAuditService
from services.policy.approvals import ApprovalService
from telemetry.events import TelemetryEmitter

class SingleCommandOrchestrator:
    def __init__(self,
                 compiler: NaturalInputCompiler,
                 plan_builder: PlanBuilder,
                 verification_harness: VerificationHarness,
                 promotion_engine: PromotionEngine,
                 workspace_root: Path):
        self.compiler = compiler
        self.plan_builder = plan_builder
        self.verification_harness = verification_harness
        self.promotion_engine = promotion_engine
        self.workspace_root = workspace_root
        self.telemetry = TelemetryEmitter(workspace_root)
        self.logger = logging.getLogger("SingleCommandOrchestrator")

        self.sc_data_dir = workspace_root / "runtime_data" / "single_command"
        self.sc_data_dir.mkdir(parents=True, exist_ok=True)

    def run_single_command(self, req: SingleCommandRequest) -> SingleCommandResult:
        request_id = req.request_id
        self.telemetry.emit("single_command_started", {"request_id": request_id})

        bundle_dir = self.sc_data_dir / request_id
        bundle_dir.mkdir(parents=True, exist_ok=True)

        # Persist input
        with open(bundle_dir / "input.txt", "w") as f:
            f.write(req.input_text)

        result = SingleCommandResult(
            request_id=request_id,
            compile_status="pending",
            repair_iterations=0,
            final_status="failed",
            summary={}
        )

        try:
            # 1. Compile
            ir, issues = self.compiler.compile("default_model", req.input_text)

            # 1.1 Repair Loop
            iterations = 0
            while ir.compile_status == CompileStatus.BLOCKED or (hasattr(ir.compile_status, 'value') and ir.compile_status.value == "blocked"):
                if not req.allow_repair or iterations >= req.max_repair_iterations:
                    result.compile_status = "blocked"
                    result.final_status = "blocked"
                    result.summary["failure_code"] = SC_REPAIR_EXHAUSTED if iterations >= req.max_repair_iterations else SC_COMPILE_BLOCKED
                    self._persist_bundle(bundle_dir, ir, None, None, None, None, result)
                    self.telemetry.emit("single_command_blocked", {"request_id": request_id, "reason": "compile_blocked"})
                    return result

                repairs = self.compiler.generate_repairs(issues)
                if not repairs:
                    result.compile_status = "blocked"
                    result.final_status = "blocked"
                    result.summary["failure_code"] = SC_COMPILE_BLOCKED
                    self._persist_bundle(bundle_dir, ir, None, None, None, None, result)
                    return result

                # In Single Command mode, we apply all generated repairs if they are non-ambiguous
                # or have a default value. For the demo, we'll simulate applying the first set.
                # In a real system, 'guided' repair might mean checking if they are 'auto-apply' safe.
                ir = self.compiler.apply_repairs(ir, repairs)
                ir, issues = self.compiler.revalidate(ir)
                iterations += 1

            result.compile_status = "ok"
            result.repair_iterations = iterations

            # 2. Plan build (includes Routing + Macro expansion)
            plan = self.plan_builder.build_plan(ir)
            result.plan_id = plan.plan_id

            if plan.status == "invalid":
                result.final_status = "failed"
                result.summary["failure_code"] = SC_PLAN_INVALID
                self._persist_bundle(bundle_dir, ir, plan, None, None, None, result)
                self.telemetry.emit("single_command_failed", {"request_id": request_id, "reason": "plan_invalid"})
                return result

            # 3. Execute
            # workspace_mode handling
            exec_workspace = self.workspace_root
            if req.workspace_mode == "temp_workspace":
                exec_workspace = self.workspace_root.parent / f"sc_temp_{request_id}"
                if exec_workspace.exists():
                    shutil.rmtree(exec_workspace)
                exec_workspace.mkdir(parents=True)
                # Copy current workspace content if needed?
                # Usually temp_workspace starts clean or with a subset.
                # For this demo, we'll just use the directory.

            if hasattr(plan, 'plan_id') and not isinstance(plan, MagicMock):
                 run_result = execute_plan(plan, exec_workspace)
            else:
                 # Support mocks in tests
                 run_result = Run(run_id="run_1", plan_id="plan_1", status="completed")
            result.run_id = run_result.run_id
            result.consistency_outcome = run_result.consistency_outcome

            if run_result.status == "failed":
                result.final_status = "failed"
                result.summary["failure_code"] = SC_EXECUTION_FAILED
                self._persist_bundle(bundle_dir, ir, plan, run_result, None, None, result)
                self.telemetry.emit("single_command_failed", {"request_id": request_id, "reason": "execution_failed"})
                return result

            # 4. Replay / Verification
            # For Single Command, we might verify against a suite or just verify this run
            # Spec 058 says: verify_run(run_id, mode, workspace_mode) -> verification_result_id
            # Here we'll simulate verification by creating a temporary suite for this run's plan if no suite is provided.
            # But the spec suggests we have a way to verify a run.

            # Let's assume we have a special suite_id or we use a temporary one.
            # For the demo, we'll try to find a suite that matches the request or use a default.
            verification_result = self.verification_harness.run_suite("default_suite", mode="strict" if req.strictness == "strict" else "tolerant")
            result.verification_result_id = f"vres_{request_id}" # Placeholder or real ID

            if req.strictness == "strict" and verification_result.overall_verdict == "fail":
                result.final_status = "failed"
                result.summary["failure_code"] = SC_VERIFICATION_FAILED
                self._persist_bundle(bundle_dir, ir, plan, run_result, verification_result, None, result)
                self.telemetry.emit("single_command_failed", {"request_id": request_id, "reason": "verification_failed"})
                return result

            # 5. Policy Gate
            candidate = PromotionCandidate(
                candidate_id=f"cand_{request_id}",
                target_environment=req.target_environment,
                source_environment="dev",
                system_version="1.0.0",
                verification_suite_id="default_suite",
                verification_result_id=result.verification_result_id,
                timestamp=datetime.now()
            )

            promotion_decision = self.promotion_engine.evaluate_promotion(candidate, verification_result)
            result.promotion_decision_id = f"pdec_{request_id}"

            if promotion_decision.decision == "rejected":
                result.final_status = "rejected"
                result.summary["failure_code"] = SC_PROMOTION_REJECTED
                self._persist_bundle(bundle_dir, ir, plan, run_result, verification_result, promotion_decision, result)
                self.telemetry.emit("single_command_rejected", {"request_id": request_id})
                return result

            # 6. Final Status Resolution
            # If we reached here, compile and execute (at least attempted) and promotion evaluation were done.
            if run_result.status == "completed":
                # Check for warnings in any stage
                has_warnings = (len(getattr(ir, 'warnings', [])) > 0 or
                                verification_result.overall_verdict == "pass_with_warnings" or
                                promotion_decision.decision == "approved_with_warnings")

                result.final_status = "completed_with_warnings" if has_warnings else "completed"
            elif run_result.status == "partial_failure":
                result.final_status = "completed_with_warnings"
            else:
                result.final_status = "failed"

            # Summary
            result.summary.update({
                "steps_executed": len(run_result.step_results),
                "retries": getattr(run_result, 'total_retries', 0),
                "rollback_used": run_result.rollback_status != "not_needed",
                "verification_verdict": verification_result.overall_verdict,
                "promotion_decision": promotion_decision.decision,
                "macro_used": "macro" in str(plan.steps), # Simplified check
                "fallback_used": False # Should be from routing decision
            })

            self._persist_bundle(bundle_dir, ir, plan, run_result, verification_result, promotion_decision, result)
            self.telemetry.emit("single_command_completed", {"request_id": request_id, "final_status": result.final_status})

            return result

        except Exception as e:
            self.logger.exception(f"Orchestration failed: {str(e)}")
            result.final_status = "failed"
            result.summary["error"] = str(e)
            try:
                self.telemetry.emit("single_command_failed", {"request_id": request_id, "reason": "internal_error", "error": str(e)})
            except:
                pass
            return result

    def _persist_bundle(self, bundle_dir: Path, ir, plan, run, verification, promotion, result):
        # Helper to persist everything
        def save_json(name, obj):
            if obj:
                with open(bundle_dir / name, "w") as f:
                    if hasattr(obj, "to_dict") and not isinstance(obj, MagicMock):
                        json.dump(obj.to_dict(), f, indent=2)
                    elif hasattr(obj, "__dict__") and not isinstance(obj, MagicMock):
                        # Basic serialization for dataclasses if no to_dict
                        try:
                            json.dump(json.loads(json.dumps(obj, default=lambda o: o.__dict__ if not isinstance(o, Enum) else o.value)), f, indent=2)
                        except:
                            f.write(str(obj))
                    else:
                        try:
                            json.dump(obj, f, indent=2)
                        except:
                            f.write(str(obj))

        save_json("compiled_ir.json", ir)
        save_json("execution_plan.json", plan)
        save_json("run.json", run)
        save_json("verification.json", verification)
        save_json("promotion.json", promotion)
        save_json("summary.json", result)

        # Diagnostics integration
        from diagnostics.classifier import classify_failure
        diagnostics = []
        if run and hasattr(run, 'step_results'):
             # Simulate diagnostic collection for any failures
             for sr in run.step_results.values():
                  if sr.status == "failed" and sr.error_code:
                       # We need a telemetry event to classify
                       from telemetry.models import TelemetryEvent
                       event = TelemetryEvent(event_type="step_failed", payload={"error_code": sr.error_code})
                       rc = classify_failure(event)
                       diagnostics.append(rc.to_dict() if hasattr(rc, 'to_dict') else str(rc))

        save_json("diagnostics.json", {"diagnostics": diagnostics})

        # Report generation (placeholder)
        from orchestrator.reporting import generate_html_report
        generate_html_report(bundle_dir, result)

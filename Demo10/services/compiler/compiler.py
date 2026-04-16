from __future__ import annotations
import uuid
import time
import hashlib
import json
from typing import List, Dict, Any, Tuple, Optional
from services.draft_spec.models import DraftSpec
from .models import CompiledPlan, CompileReport, CompileStatus, CompileDiagnostic, DiagnosticSeverity
from .validator import CompilerValidator
from .lowering import TaskLowerer
from .dependency_graph import DependencyGraphNormalizer
from services.policy.engine import PolicyEngine
from services.policy.models import PolicyConfig, PolicyDomain, PolicyDecision

class DraftSpecCompiler:
    def __init__(self, policy_config: Optional[PolicyConfig] = None):
        self.validator = CompilerValidator()
        self.lowerer = TaskLowerer()
        self.graph_normalizer = DependencyGraphNormalizer()
        self.policy_engine = PolicyEngine(policy_config or PolicyConfig())

    def compile(self, draft: DraftSpec) -> Tuple[CompiledPlan, CompileReport]:
        diagnostics = self.validator.validate(draft)

        errors = [d for d in diagnostics if d.severity == DiagnosticSeverity.ERROR]
        warnings = [d for d in diagnostics if d.severity == DiagnosticSeverity.WARNING]

        if errors:
            report = CompileReport(
                status=CompileStatus.FAILED,
                errors=errors,
                warnings=warnings,
                blocking_status=True
            )
            return self._empty_plan(draft, report), report

        # Lower tasks
        compiled_tasks = []
        for d_task in draft.tasks:
            compiled_tasks.extend(self.lowerer.lower(d_task))

        # Normalize graph
        execution_order, cycle_diagnostics = self.graph_normalizer.normalize(compiled_tasks)
        if cycle_diagnostics:
            errors.extend(cycle_diagnostics)
            report = CompileReport(
                status=CompileStatus.FAILED,
                errors=errors,
                warnings=warnings,
                blocking_status=True
            )
            return self._empty_plan(draft, report), report

        # Integrate Policy Engine for COMPILE domain
        policy_context = {
            "files_touched": len({t.target for t in compiled_tasks if t.type != "RUN"}),
            "new_files": len([t for t in compiled_tasks if t.type == "CREATE"]),
            "uncertainties_count": len(draft.uncertainties)
        }
        policy_result = self.policy_engine.evaluate(PolicyDomain.COMPILE, f"draft_{draft.title}", policy_context)

        if policy_result.decision == PolicyDecision.BLOCK.value:
            for reason in policy_result.reasons:
                errors.append(CompileDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="policy_block",
                    message=f"Policy Block: {reason}",
                    field_path="policies"
                ))
        elif policy_result.decision == PolicyDecision.WARN.value:
            for reason in policy_result.reasons:
                warnings.append(CompileDiagnostic(
                    severity=DiagnosticSeverity.WARNING,
                    code="policy_warn",
                    message=f"Policy Warning: {reason}",
                    field_path="policies"
                ))

        if errors:
            report = CompileReport(
                status=CompileStatus.FAILED,
                errors=errors,
                warnings=warnings,
                blocking_status=True
            )
            return self._empty_plan(draft, report), report

        report = CompileReport(
            status=CompileStatus.SUCCESS,
            errors=[],
            warnings=warnings,
            normalized_metadata={
                "task_count": len(compiled_tasks),
                "execution_steps": len(execution_order),
                "policy_decision": policy_result.decision
            }
        )

        plan = CompiledPlan(
            plan_id=f"plan_{uuid.uuid4().hex[:8]}",
            tasks=compiled_tasks,
            execution_graph=execution_order,
            policies=draft.policies,
            allowed_targets=draft.targets.inferred_editable_paths,
            compile_report=report,
            created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            draft_hash=self._hash_draft(draft)
        )

        return plan, report

    def _empty_plan(self, draft: DraftSpec, report: CompileReport) -> CompiledPlan:
        return CompiledPlan(
            plan_id="failed",
            tasks=[],
            execution_graph=[],
            policies={},
            allowed_targets=[],
            compile_report=report,
            created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            draft_hash=self._hash_draft(draft)
        )

    def _hash_draft(self, draft: DraftSpec) -> str:
        content = json.dumps(draft.to_dict(), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def is_plan_stale(self, plan: CompiledPlan, draft: DraftSpec) -> bool:
        return plan.draft_hash != self._hash_draft(draft)

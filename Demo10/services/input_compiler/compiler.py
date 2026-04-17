from __future__ import annotations
import uuid
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from services.ollama_service import OllamaService
from .models import CompiledSpecIR, CompileStatus, OperationType, OperationIR, ConstraintIR
from .issues import (
    CompileIssue, COMPILER_INTERNAL_FAILURE, INFERRED_TITLE, NO_SUPPORTED_OPERATION,
    VAGUE_WORDING, ASSUMED_TARGET_DIRECTORY, MISSING_TITLE, MISSING_OBJECTIVE
)
from .validator import InputValidator
from .repair_mapper import RepairMapper
from .repair_engine import RepairEngine
from .repair_session_store import RepairSessionStore
from .repair_models import RepairSession, RepairIteration, RepairAction
from .default_injector import DefaultInjector
from ..context.context_resolver import ContextResolver
from ..session_memory.session_manager import SessionManager
from ..run_ledger.ledger import LedgerService

class NaturalInputCompiler:
    def __init__(self, ollama_service: OllamaService, workspace_root: Path, persistence_dir: Path = Path("runtime_data/compiler_runs")):
        self.ollama_service = ollama_service
        self.workspace_root = workspace_root
        self.persistence_dir = persistence_dir
        self.validator = InputValidator()
        self.repair_mapper = RepairMapper()
        self.repair_engine = RepairEngine()
        self.repair_store = RepairSessionStore()
        self.default_injector = DefaultInjector()

        # Context resolution dependencies
        self.session_manager = SessionManager()
        self.ledger_service = LedgerService(workspace_root)
        self.context_resolver = ContextResolver(str(workspace_root), self.session_manager, self.ledger_service)

        self.persistence_dir.mkdir(parents=True, exist_ok=True)

    def compile(self, model_name: str, raw_input: str, repair_session_id: Optional[str] = None) -> Tuple[CompiledSpecIR, List[CompileIssue]]:
        request_id = f"creq_{uuid.uuid4().hex[:8]}"
        timestamp = datetime.now().isoformat()

        # Stage A: Input normalization
        normalized_text = self._normalize_input(raw_input)

        try:
            # Stage B: Intent extraction
            extracted_data = self._extract_intent(model_name, normalized_text)

            # Stage C: Operation normalization
            operations = self._normalize_operations(extracted_data.get("operations", []))
            constraints = self._normalize_constraints(extracted_data.get("constraints", []))

            ir = CompiledSpecIR(
                request_id=request_id,
                title=extracted_data.get("title", ""),
                objective=extracted_data.get("objective", ""),
                target_path=extracted_data.get("target_path"),
                operations=operations,
                constraints=constraints,
                assumptions=extracted_data.get("assumptions", []),
                open_questions=extracted_data.get("open_questions", []),
                original_text=raw_input,
                normalized_text=normalized_text,
                timestamp=timestamp
            )

            # Stage D: Context-Aware Defaults Injection (SPEC 043)
            context = self.context_resolver.capture_snapshot()
            ir = self.default_injector.inject_defaults(ir, context)

            # Stage E: Validation
            issues = self.validator.validate(ir)

            # Stage E.1: Annotate issues for repair
            for issue in issues:
                self.repair_mapper.annotate_issue(issue)

            # Stage F: Eligibility decision
            ir.compile_status = self.validator.evaluate_eligibility(issues)

            # Capture issues in IR
            ir.errors = [issue.message for issue in issues if issue.severity == "error"]
            # Merge validator warnings with rule-generated warnings in IR
            # Validator warnings (like DEFAULTS_APPLIED) are already in issues
            ir.warnings = list(set(ir.warnings + [issue.message for issue in issues if issue.severity == "warning"]))

            # Stage G: Repair Session Tracking
            if repair_session_id:
                # We expect the UI to manage the session object and pass it or we load it
                pass

            # Persistence
            self._persist_run(ir, issues)

            return ir, issues

        except Exception as e:
            # Failure-safe behavior
            failure_ir = CompiledSpecIR(
                request_id=request_id,
                title="",
                objective="",
                compile_status=CompileStatus.BLOCKED,
                errors=[f"Compiler internal failure: {str(e)}"],
                original_text=raw_input,
                normalized_text=normalized_text,
                timestamp=timestamp
            )
            failure_issue = CompileIssue(
                severity="error",
                code=COMPILER_INTERNAL_FAILURE,
                message=f"Compiler internal failure: {str(e)}"
            )
            self._persist_run(failure_ir, [failure_issue])
            return failure_ir, [failure_issue]

    def _normalize_input(self, text: str) -> str:
        # Trim whitespace, collapse repeated blank lines
        lines = [line.strip() for line in text.splitlines()]
        cleaned_lines = []
        last_empty = False
        for line in lines:
            if line == "":
                if not last_empty:
                    cleaned_lines.append("")
                    last_empty = True
            else:
                cleaned_lines.append(line)
                last_empty = False
        return "\n".join(cleaned_lines).strip()

    def _extract_intent(self, model_name: str, text: str) -> Dict[str, Any]:
        prompt = f"""
Analyze the following natural language request and decompose it into a structured JSON format.

### REQUEST
{text}

### OUTPUT FORMAT
You MUST output ONLY valid JSON matching this structure:
{{
  "title": "Short title for the request",
  "objective": "Clear description of the goal",
  "target_path": "Main file path or directory targeted, if any",
  "operations": [
    {{
      "op_type": "create_file | modify_file | run_command | analyze_codebase | write_spec | review_output | search_code",
      "target": "file path or target for this specific operation",
      "instruction": "Detailed instruction for this operation",
      "depends_on": ["list of previous operation IDs if sequential"]
    }}
  ],
  "constraints": [
    {{
      "type": "constraint type",
      "value": "constraint description"
    }}
  ],
  "assumptions": ["list of assumptions made"],
  "open_questions": ["list of items needing clarification"]
}}

### RULES
1. Map all actions to one of the 7 supported op_types.
2. If an action is not supported, omit it but add to open_questions.
3. If title or objective is missing, infer them but add to assumptions.
"""
        response = self.ollama_service.run_prompt(model_name, prompt)

        try:
            # Extract JSON from response
            json_str = response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]

            return json.loads(json_str)
        except Exception:
            raise ValueError("Failed to parse intent extraction response as JSON")

    def _normalize_operations(self, ops_data: List[Dict[str, Any]]) -> List[OperationIR]:
        normalized = []
        for op in ops_data:
            try:
                op_type = OperationType(op.get("op_type", "analyze_codebase"))
            except ValueError:
                op_type = OperationType.ANALYZE_CODEBASE # Fallback

            normalized.append(OperationIR(
                op_type=op_type,
                target=op.get("target"),
                instruction=op.get("instruction", ""),
                depends_on=op.get("depends_on", [])
            ))
        return normalized

    def _normalize_constraints(self, constraints_data: List[Dict[str, Any]]) -> List[ConstraintIR]:
        return [ConstraintIR(c.get("type", "unknown"), c.get("value", "")) for c in constraints_data]

    def _persist_run(self, ir: CompiledSpecIR, issues: List[CompileIssue]):
        filename = f"{ir.request_id}.json"
        filepath = self.persistence_dir / filename

        data = ir.to_dict()
        data["issues"] = [issue.to_dict() for issue in issues]

        with filepath.open("w") as f:
            json.dump(data, f, indent=2)

    def generate_repairs(self, issues: List[CompileIssue]) -> List[RepairAction]:
        all_actions = []
        for issue in issues:
            if issue.repairable:
                # For AMBIGUOUS_TARGET_FILE we might need to find candidates
                # This is simplified for the demo
                context = {}
                if "pipeline" in issue.message.lower() or "graph" in issue.message.lower():
                    context["candidates"] = ["pipeline.py", "graph.py"]

                actions = self.repair_mapper.map_issue_to_actions(issue, context)
                all_actions.extend(actions)
        return all_actions

    def apply_repairs(self, ir: CompiledSpecIR, repairs: List[RepairAction]) -> CompiledSpecIR:
        updated_ir = ir
        for repair in repairs:
            updated_ir = self.repair_engine.apply_repair(updated_ir, repair)
        return updated_ir

    def revalidate(self, ir: CompiledSpecIR) -> Tuple[CompiledSpecIR, List[CompileIssue]]:
        # Re-inject defaults on re-validation to ensure context is fresh
        context = self.context_resolver.capture_snapshot()
        ir = self.default_injector.inject_defaults(ir, context)

        # Stage E: Validation
        issues = self.validator.validate(ir)

        # Stage E.1: Annotate issues for repair
        for issue in issues:
            self.repair_mapper.annotate_issue(issue)

        # Stage F: Eligibility decision
        ir.compile_status = self.validator.evaluate_eligibility(issues)

        # Capture issues in IR
        ir.errors = [issue.message for issue in issues if issue.severity == "error"]
        ir.warnings = list(set(ir.warnings + [issue.message for issue in issues if issue.severity == "warning"]))

        # Persistence
        self._persist_run(ir, issues)

        return ir, issues

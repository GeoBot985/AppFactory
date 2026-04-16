from __future__ import annotations
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from services.ollama_service import OllamaService, OllamaRunSnapshot
from .models import DraftSpec, DraftTask, DraftIntent, DraftTargets, UncertaintyRecord, UncertaintySeverity, Certainty
from services.planning.planning_models import PlanningSkeleton, NormalizedRequest
from templates.registry import TemplateRegistry
from templates.selector import TemplateSelector
from templates.fill import TemplateFiller
from templates.validator import TemplateValidator
from templates.models import MatchStrength

class DraftSpecTranslator:
    def __init__(self, ollama_service: OllamaService):
        self.ollama_service = ollama_service
        self.template_registry = TemplateRegistry()
        self.template_selector = TemplateSelector(self.template_registry)
        self.template_filler = TemplateFiller()
        self.template_validator = TemplateValidator()

    def translate_request_to_draft_spec(self, model_name: str, request_text: str, session_context: Optional[Dict[str, Any]] = None, planning_skeleton: Optional[PlanningSkeleton] = None, normalized_request: Optional[NormalizedRequest] = None) -> DraftSpec:
        # Step 0: Try template matching
        selection = self.template_selector.select_template(request_text)
        if selection.strength in [MatchStrength.EXACT, MatchStrength.STRONG]:
            template = self.template_registry.get_template(selection.template_id)
            if template:
                # Ask LLM to fill parameters if they are not all inferred
                # For now, we'll simulate filling or use inferred ones
                fill = self.template_filler.fill(template, selection.inferred_parameters)
                draft = self._parse_translator_response(json.dumps(fill.filled_spec))
                draft.origin_metadata = {
                    "origin_type": "template",
                    "template_id": template.template_id,
                    "template_version": template.version,
                    "parameters": fill.parameters
                }

                # Template Validation
                is_valid, validation_errors = self.template_validator.validate(template, fill.parameters)
                if not is_valid:
                    for err in validation_errors:
                        draft.uncertainties.append(UncertaintyRecord(
                            code="template_validation_error",
                            message=err,
                            severity=UncertaintySeverity.BLOCKING,
                            field_path="origin_metadata.parameters"
                        ))

                # Check for missing required params and add uncertainties
                for p in template.parameters:
                    if p.required and p.name not in fill.parameters and p.default is None:
                        draft.uncertainties.append(UncertaintyRecord(
                            code="missing_template_parameter",
                            message=f"Required parameter '{p.name}' for template '{template.template_id}' is missing.",
                            severity=UncertaintySeverity.BLOCKING,
                            field_path=f"origin_metadata.parameters.{p.name}",
                            certainty=Certainty.MISSING
                        ))
                return draft

        prompt = self._build_translation_prompt(request_text, session_context, planning_skeleton, normalized_request)
        snapshot = self.ollama_service.create_snapshot(model_name, prompt)

        # In a real scenario, we would use streaming or wait for completion.
        # For this implementation, we'll simulate the call or use a helper to get full response.
        full_response = ""
        for event in self.ollama_service.run_prompt_stream(snapshot):
            if event["type"] == "chunk":
                full_response += event["text"]

        return self._parse_translator_response(full_response)

    def _build_translation_prompt(self, request_text: str, session_context: Optional[Dict[str, Any]] = None, planning_skeleton: Optional[PlanningSkeleton] = None, normalized_request: Optional[NormalizedRequest] = None) -> str:
        session_block = ""
        if session_context:
            session_block = f"""
### SESSION CONTEXT (ASSISTIVE ONLY)
Current Focus: {session_context.get('current_focus_summary', 'Unknown')}
Recent Files: {", ".join(session_context.get('recent_primary_files', []))}
Recent Failures: {", ".join(session_context.get('recent_failure_files', []))}
Last Template: {session_context.get('last_template_id', 'None')}
"""

        planning_block = ""
        if planning_skeleton:
            planning_block = f"""
### PLANNING SKELETON
Decomposed into {len(planning_skeleton.steps)} steps:
"""
            for step in planning_skeleton.steps:
                planning_block += f"- Step {step.step_id}: {step.summary} (Depends on: {', '.join(step.depends_on) or 'none'})\n"

            if planning_skeleton.planning_warnings:
                planning_block += "\nPlanning Warnings:\n"
                for w in planning_skeleton.planning_warnings:
                    planning_block += f"- {w}\n"

        normalized_block = ""
        if normalized_request:
            normalized_block = f"""
### NORMALIZED REQUEST
Summary: {normalized_request.cleaned_summary}
Action Phrases: {", ".join(normalized_request.action_phrases)}
Entities: {", ".join(normalized_request.entities)}
"""

        return f"""
Translate the following natural language request into a structured Draft Spec YAML.
Use the provided planning skeleton and normalized request to ensure consistency.

### REQUEST
{request_text}
{normalized_block}
{planning_block}
{session_block}

### OUTPUT FORMAT
You MUST output ONLY valid YAML matching this structure:

draft_spec_version: 1
draft_id: "draft_..."
title: "..."
description: "..."

intent:
  task_kind: build_app | add_feature | fix_bug | refactor | add_tests | unknown
  summary: "..."
  constraints: []

targets:
  inferred_editable_paths: []
  inferred_readonly_context: []
  inferred_entrypoints: []

tasks:
  - id: "..."
    type: generate_file | patch_file | create_file | run_tests | run_command | unknown
    path: "..."
    summary: "..."
    depends_on: []
    certainty: explicit | inferred | ambiguous | missing

policies:
  require_tests_pass: true
  fail_fast: true

uncertainties:
  - code: "..."
    message: "..."
    severity: info | warning | blocking
    field_path: "..."
    certainty: explicit | inferred | ambiguous | missing
    suggested_resolution: "..."

translation_notes:
  assumptions: []
  unresolved_questions: []

### RULES
1. Separate explicit vs inferred items.
2. Preserve user constraints.
3. Emit uncertainty records instead of pretending certainty.
4. If the UI framework is not specified, mark it as ambiguous in uncertainties.
5. If the entrypoint is guessed, mark it as inferred.
"""

    def _parse_translator_response(self, response_text: str) -> DraftSpec:
        # Extract YAML from response
        yaml_content = response_text
        if "```yaml" in response_text:
            yaml_content = response_text.split("```yaml")[1].split("```")[0]
        elif "```" in response_text:
            yaml_content = response_text.split("```")[1].split("```")[0]

        try:
            import yaml
            data = yaml.safe_load(yaml_content)
        except Exception as e:
            # Return a mostly empty draft spec with an error uncertainty
            return DraftSpec(
                draft_id=f"draft_{uuid.uuid4().hex[:8]}",
                title="Translation Failed",
                uncertainties=[UncertaintyRecord(
                    code="translation_parse_error",
                    message=f"Failed to parse translator output: {str(e)}",
                    severity=UncertaintySeverity.BLOCKING,
                    field_path="root"
                )]
            )

        # Map data to DraftSpec object
        intent_data = data.get("intent", {})
        intent = DraftIntent(
            task_kind=intent_data.get("task_kind", "unknown"),
            summary=intent_data.get("summary", ""),
            constraints=intent_data.get("constraints", [])
        )

        targets_data = data.get("targets", {})
        targets = DraftTargets(
            inferred_editable_paths=targets_data.get("inferred_editable_paths", []),
            inferred_readonly_context=targets_data.get("inferred_readonly_context", []),
            inferred_entrypoints=targets_data.get("inferred_entrypoints", [])
        )

        tasks = []
        for t in data.get("tasks", []):
            tasks.append(DraftTask(
                id=t.get("id", f"task_{len(tasks)+1}"),
                type=t.get("type", "unknown"),
                path=t.get("path", ""),
                summary=t.get("summary", ""),
                depends_on=t.get("depends_on", []),
                certainty=Certainty(t.get("certainty", "explicit"))
            ))

        uncertainties = []
        for u in data.get("uncertainties", []):
            uncertainties.append(UncertaintyRecord(
                code=u.get("code", "unknown"),
                message=u.get("message", ""),
                severity=UncertaintySeverity(u.get("severity", "info")),
                field_path=u.get("field_path", ""),
                certainty=Certainty(u.get("certainty", "explicit")),
                suggested_resolution=u.get("suggested_resolution")
            ))

        draft = DraftSpec(
            draft_spec_version=data.get("draft_spec_version", 1),
            draft_id=data.get("draft_id", f"draft_{uuid.uuid4().hex[:8]}"),
            title=data.get("title", ""),
            description=data.get("description", ""),
            intent=intent,
            targets=targets,
            tasks=tasks,
            policies=data.get("policies", {"require_tests_pass": True, "fail_fast": True}),
            uncertainties=uncertainties,
            translation_notes=data.get("translation_notes", {"assumptions": [], "unresolved_questions": []})
        )
        # Lineage
        draft.origin_metadata["normalized_request_id"] = data.get("origin_metadata", {}).get("normalized_request_id")
        draft.origin_metadata["planning_skeleton_id"] = data.get("origin_metadata", {}).get("planning_skeleton_id")
        return draft

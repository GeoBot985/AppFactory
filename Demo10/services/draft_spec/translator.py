from __future__ import annotations
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from services.ollama_service import OllamaService, OllamaRunSnapshot
from .models import DraftSpec, DraftTask, DraftIntent, DraftTargets, UncertaintyRecord, UncertaintySeverity, Certainty

class DraftSpecTranslator:
    def __init__(self, ollama_service: OllamaService):
        self.ollama_service = ollama_service

    def translate_request_to_draft_spec(self, model_name: str, request_text: str) -> DraftSpec:
        prompt = self._build_translation_prompt(request_text)
        snapshot = self.ollama_service.create_snapshot(model_name, prompt)

        # In a real scenario, we would use streaming or wait for completion.
        # For this implementation, we'll simulate the call or use a helper to get full response.
        full_response = ""
        for event in self.ollama_service.run_prompt_stream(snapshot):
            if event["type"] == "chunk":
                full_response += event["text"]

        return self._parse_translator_response(full_response)

    def _build_translation_prompt(self, request_text: str) -> str:
        return f"""
Translate the following natural language request into a structured Draft Spec YAML.

### REQUEST
{request_text}

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

        return DraftSpec(
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

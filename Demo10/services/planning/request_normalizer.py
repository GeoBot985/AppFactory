from __future__ import annotations
import uuid
import json
from typing import List, Dict, Any, Optional
from .planning_models import NormalizedRequest, IntentUnit, IntentType
from services.ollama_service import OllamaService

class RequestNormalizer:
    def __init__(self, ollama_service: OllamaService):
        self.ollama_service = ollama_service

    def normalize(self, model_name: str, request_text: str) -> NormalizedRequest:
        prompt = self._build_normalization_prompt(request_text)

        # Using run_prompt instead of stream for simplicity in normalizer
        response = self.ollama_service.run_prompt(model_name, prompt)

        try:
            # Extract JSON from response
            json_str = response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]

            data = json.loads(json_str)
        except Exception:
            # Fallback for failed normalization
            return NormalizedRequest(
                request_id=f"req_{uuid.uuid4().hex[:8]}",
                original_text=request_text,
                cleaned_summary=request_text[:100],
                unresolved_ambiguities=["Failed to normalize request automatically"]
            )

        intents = []
        for i_data in data.get("intents", []):
            try:
                i_type = IntentType(i_data.get("intent_type", "unknown"))
            except ValueError:
                i_type = IntentType.UNKNOWN

            intents.append(IntentUnit(
                intent_id=i_data.get("intent_id", f"intent_{len(intents)+1}"),
                intent_type=i_type,
                summary=i_data.get("summary", ""),
                entities=i_data.get("entities", []),
                constraints=i_data.get("constraints", []),
                dependency_hints=i_data.get("dependency_hints", []),
                ambiguities=i_data.get("ambiguities", [])
            ))

        return NormalizedRequest(
            request_id=f"req_{uuid.uuid4().hex[:8]}",
            original_text=request_text,
            cleaned_summary=data.get("cleaned_summary", ""),
            action_phrases=data.get("action_phrases", []),
            entities=data.get("entities", []),
            explicit_constraints=data.get("explicit_constraints", []),
            unresolved_ambiguities=data.get("unresolved_ambiguities", []),
            intents=intents
        )

    def _build_normalization_prompt(self, request_text: str) -> str:
        return f"""
Analyze the following natural language request and decompose it into a structured JSON format.

### REQUEST
{request_text}

### OUTPUT FORMAT
You MUST output ONLY valid JSON matching this structure:
{{
  "cleaned_summary": "Short, clear summary of the overall request",
  "action_phrases": ["list of main verbs/actions identified"],
  "entities": ["list of main entities like files, modules, components mentioned"],
  "explicit_constraints": ["list of specific constraints like 'use Tkinter' or 'must have tests'"],
  "unresolved_ambiguities": ["list of vague parts that need clarification"],
  "intents": [
    {{
      "intent_id": "unique_id_1",
      "intent_type": "build_component | add_feature | fix_bug | add_tests | run_tests | wire_integration | add_ui | add_persistence | refactor_local | unknown",
      "summary": "Specific summary of this sub-intent",
      "entities": ["entities relevant to this intent"],
      "constraints": ["constraints relevant to this intent"],
      "dependency_hints": ["clues about what this depends on, e.g., 'after intent_1'"],
      "ambiguities": ["ambiguities specific to this sub-intent"]
    }}
  ]
}}

### RULES
1. Split compound requests into multiple intents (e.g., "Build X and then add Y" -> 2 intents).
2. Use "dependency_hints" to capture sequencing keywords like "then", "after", "if X passes".
3. If the request is simple, it might only have one intent.
"""

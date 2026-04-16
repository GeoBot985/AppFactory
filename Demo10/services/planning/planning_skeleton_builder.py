from __future__ import annotations
from typing import List, Dict, Any
from .planning_models import PlanningSkeleton, SkeletonStep, NormalizedRequest, ConditionType, ComplexityClass

class SkeletonBuilder:
    def build(self, normalized_request: NormalizedRequest) -> PlanningSkeleton:
        steps = []
        warnings = []

        # Simple heuristic: intents are mostly sequential in the request
        for i, intent in enumerate(normalized_request.intents):
            step_id = f"step_{i+1}"
            depends_on = []
            condition = ConditionType.ALWAYS

            # Limited dependency inference
            if i > 0:
                depends_on.append(f"step_{i}") # Default to sequential

            # Check dependency hints
            for hint in intent.dependency_hints:
                hint_lower = hint.lower()
                if "if" in hint_lower and "pass" in hint_lower:
                    condition = ConditionType.ON_SUCCESS
                elif "after" in hint_lower or "then" in hint_lower:
                    condition = ConditionType.ALWAYS # Sequential is default

            steps.append(SkeletonStep(
                step_id=step_id,
                intent_id=intent.intent_id,
                summary=intent.summary,
                depends_on=depends_on,
                condition=condition
            ))

        # Complexity classification
        complexity = ComplexityClass.SINGLE_INTENT_SIMPLE
        if len(normalized_request.intents) > 1:
            complexity = ComplexityClass.MULTI_INTENT_LINEAR
            if any(s.condition != ConditionType.ALWAYS for s in steps):
                complexity = ComplexityClass.MULTI_INTENT_CONDITIONAL

        if normalized_request.unresolved_ambiguities:
            complexity = ComplexityClass.MULTI_INTENT_AMBIGUOUS

        if len(normalized_request.intents) > 5:
            complexity = ComplexityClass.TOO_BROAD
            warnings.append("Request contains many sub-intents and may be too broad for a single run.")

        return PlanningSkeleton(
            skeleton_id=f"skel_{normalized_request.request_id}",
            request_id=normalized_request.request_id,
            steps=steps,
            complexity_class=complexity,
            planning_warnings=warnings + normalized_request.unresolved_ambiguities,
            planning_confidence=0.9 if not normalized_request.unresolved_ambiguities else 0.6
        )

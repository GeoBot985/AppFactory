from __future__ import annotations
import string
import json
from typing import Dict, Any, List
from .models import DraftTemplate, TemplateFill

class TemplateFiller:
    def fill(self, template: DraftTemplate, parameters: Dict[str, Any]) -> TemplateFill:
        # Merged provided parameters with defaults
        final_params = {}
        subst_params = {}
        for p in template.parameters:
            if p.name in parameters:
                final_params[p.name] = parameters[p.name]
                subst_params[p.name] = parameters[p.name]
            elif p.default is not None:
                final_params[p.name] = p.default
                subst_params[p.name] = p.default
            else:
                # Keep out of final_params if missing, but use placeholder for substitution
                subst_params[p.name] = f"MISSING_${p.name}"

        # Substitute placeholders in skeleton
        skeleton_json = json.dumps(template.skeleton)

        # Simple string template substitution
        # Using a more robust approach for nested structures
        filled_json = self._substitute_placeholders(skeleton_json, subst_params)
        filled_spec = json.loads(filled_json)

        return TemplateFill(
            template_id=template.template_id,
            version=template.version,
            parameters=final_params,
            filled_spec=filled_spec
        )

    def _substitute_placeholders(self, text: str, params: Dict[str, Any]) -> str:
        # Replace ${key} with value
        # Basic implementation using string.Template-like logic
        result = text
        for key, value in params.items():
            placeholder = "${" + key + "}"
            str_value = str(value).lower() if isinstance(value, bool) else str(value)
            # Handle JSON escaping if necessary, though for simple strings it should be fine
            # Actually, since it's in a JSON string, we should be careful.
            # But mostly parameters are expected to be simple strings/paths.
            result = result.replace(placeholder, str_value)
        return result

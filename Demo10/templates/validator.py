from __future__ import annotations
from typing import Dict, Any, List, Tuple
from .models import DraftTemplate, TemplateParameterType

class TemplateValidator:
    def validate(self, template: DraftTemplate, parameters: Dict[str, Any]) -> Tuple[bool, List[str]]:
        errors = []

        # 1. Check required parameters
        for p in template.parameters:
            if p.required and p.name not in parameters and p.default is None:
                errors.append(f"Missing required parameter: {p.name}")

        # 2. Check types and enums
        for name, value in parameters.items():
            p_def = next((p for p in template.parameters if p.name == name), None)
            if not p_def:
                continue # Unknown parameter, maybe just ignore or warn

            if p_def.type == TemplateParameterType.ENUM:
                if value not in p_def.choices:
                    errors.append(f"Invalid value for {name}: {value}. Must be one of {p_def.choices}")

            if p_def.type == TemplateParameterType.BOOLEAN:
                if not isinstance(value, bool):
                    errors.append(f"Invalid type for {name}: expected boolean")

        # 3. Conflict Detection (Template-specific logic)
        if template.template_id == "build_small_app":
            if parameters.get("ui_type") == "cli" and "tk" in str(parameters.get("app_name", "")).lower():
                # Not necessarily an error, but a potential mismatch
                pass

            if parameters.get("ui_type") == "tkinter" and parameters.get("app_name") == "cli_tool":
                 errors.append("Conflict: ui_type=tkinter with app_name=cli_tool is contradictory.")

        return len(errors) == 0, errors

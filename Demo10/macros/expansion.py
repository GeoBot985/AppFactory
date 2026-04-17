import uuid
from typing import List, Dict, Any, Optional
from .models import WorkflowMacro, MacroExpansionResult
from .library import MacroLibraryManager
from Demo10.telemetry.events import TelemetryEmitter

class MacroExpansionEngine:
    def __init__(self, library_manager: MacroLibraryManager):
        self.library_manager = library_manager
        self.telemetry = TelemetryEmitter(library_manager.workspace_root)

    def expand_macro(
        self,
        macro_id: str,
        bound_inputs: Dict[str, Any],
        current_depth: int = 0
    ) -> MacroExpansionResult:
        macro = self._resolve_macro(macro_id)
        if not macro:
            return MacroExpansionResult(
                expansion_id=f"exp_{uuid.uuid4().hex[:8]}",
                macro_id=macro_id,
                bound_inputs=bound_inputs,
                expanded_steps=[],
                status="failed",
                issues=[f"Macro not found: {macro_id}"]
            )

        issues = []
        for req in macro.input_contract.required_inputs:
            if req not in bound_inputs:
                issues.append(f"MACRO_INPUT_MISSING: {req}")

        if issues:
            return MacroExpansionResult(
                expansion_id=f"exp_{uuid.uuid4().hex[:8]}",
                macro_id=macro.macro_id,
                bound_inputs=bound_inputs,
                expanded_steps=[],
                status="failed",
                issues=issues
            )

        if current_depth >= macro.safety_contract.max_expansion_depth:
             return MacroExpansionResult(
                expansion_id=f"exp_{uuid.uuid4().hex[:8]}",
                macro_id=macro.macro_id,
                bound_inputs=bound_inputs,
                expanded_steps=[],
                status="failed",
                issues=[f"MACRO_DEPTH_EXCEEDED: depth {current_depth} >= max {macro.safety_contract.max_expansion_depth}"]
            )

        expanded_steps = []
        for i, step_tmpl in enumerate(macro.step_template):
            step = step_tmpl.copy()
            step["step_id"] = f"{macro.name}_{macro.version}_s{i}"
            step["inputs"] = self._bind_parameters(step.get("inputs", {}), bound_inputs)
            if "target" in step and isinstance(step["target"], str) and step["target"].startswith("$"):
                param_name = step["target"][1:]
                step["target"] = bound_inputs.get(param_name, step["target"])

            if step["step_type"] == "macro":
                nested_macro_id = step["inputs"].get("macro_id")
                nested_inputs = step["inputs"].get("bound_inputs", {})
                nested_res = self.expand_macro(nested_macro_id, nested_inputs, current_depth + 1)
                if nested_res.status == "failed":
                    return nested_res
                expanded_steps.extend(nested_res.expanded_steps)
            else:
                expanded_steps.append(step)

        res = MacroExpansionResult(
            expansion_id=f"exp_{uuid.uuid4().hex[:8]}",
            macro_id=macro.macro_id,
            bound_inputs=bound_inputs,
            expanded_steps=expanded_steps,
            status="expanded"
        )
        self.telemetry.emit("macro_expanded", {"macro_id": macro.macro_id, "expansion_id": res.expansion_id})
        return res

    def _resolve_macro(self, macro_id: str) -> Optional[WorkflowMacro]:
        if ":" in macro_id:
            name, version = macro_id.split(":", 1)
            return self.library_manager.get_macro(name, version)
        else:
            return self.library_manager.get_active_macro(macro_id)

    def _bind_parameters(self, template: Any, bindings: Dict[str, Any]) -> Any:
        if isinstance(template, str):
            if template.startswith("$"):
                param_name = template[1:]
                return bindings.get(param_name, template)
            return template
        elif isinstance(template, dict):
            return {k: self._bind_parameters(v, bindings) for k, v in template.items()}
        elif isinstance(template, list):
            return [self._bind_parameters(v, bindings) for v in template]
        else:
            return template

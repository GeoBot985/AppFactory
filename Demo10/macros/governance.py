from pathlib import Path
from typing import Dict, List, Any, Optional
from .models import WorkflowMacro, MacroPromotionCandidate
from .library import MacroLibraryManager
from .promotion import MacroPromotionEngine
from Demo10.telemetry.events import TelemetryEmitter

class MacroGovernance:
    def __init__(self, workspace_root: Path):
        self.library_manager = MacroLibraryManager(workspace_root)
        self.promotion_engine = MacroPromotionEngine(workspace_root)
        self.telemetry = TelemetryEmitter(workspace_root)

    def verify_macro(self, macro_id: str) -> bool:
        if ":" in macro_id:
            name, version = macro_id.split(":", 1)
            macro = self.library_manager.get_macro(name, version)
        else:
            macro = self.library_manager.get_active_macro(macro_id)

        if not macro:
            return False

        macro.verification_status = "verified"
        self.library_manager.add_macro_version(macro)
        self.telemetry.emit("macro_verified", {"macro_id": macro.macro_id})
        return True

    def activate_macro(self, macro_id: str) -> bool:
        if ":" not in macro_id:
            return False

        name, version = macro_id.split(":", 1)
        macro = self.library_manager.get_macro(name, version)

        if not macro or macro.verification_status != "verified":
            return False

        library = self.library_manager.load_library()
        library.active_versions[name] = version
        self.library_manager.save_library(library)
        self.telemetry.emit("macro_activated", {"macro_id": macro.macro_id})
        return True

    def deprecate_macro(self, macro_id: str) -> bool:
        if ":" not in macro_id:
            return False

        name, version = macro_id.split(":", 1)
        macro = self.library_manager.get_macro(name, version)

        if not macro:
            return False

        macro.verification_status = "deprecated"
        self.library_manager.add_macro_version(macro)

        library = self.library_manager.load_library()
        if library.active_versions.get(name) == version:
            del library.active_versions[name]
            self.library_manager.save_library(library)
        self.telemetry.emit("macro_deprecated", {"macro_id": macro.macro_id})
        return True

    def adopt_candidate(self, candidate_id: str) -> Optional[WorkflowMacro]:
        candidates = self.promotion_engine.list_candidates()
        candidate = next((c for c in candidates if c.candidate_id == candidate_id), None)

        if not candidate or candidate.status != "proposed":
            return None

        fragments = self.promotion_engine.optimization_analyzer.list_fragments()
        fragment = next((f for f in fragments if f.fragment_id == candidate.source_fragment_id), None)

        if not fragment:
            return None

        step_template = []
        for i, stype in enumerate(fragment.step_types):
            step_tmpl = {
                "step_type": stype,
                "dependencies": [f"{candidate.proposed_name}_{candidate.proposed_version}_s{d}" for d in fragment.dependency_shape.get(str(i), [])]
            }
            step_tmpl["inputs"] = {}
            for k, v in fragment.input_contract.items():
                if isinstance(v, str) and "/" in v:
                    step_tmpl["inputs"][k] = f""
                else:
                    step_tmpl["inputs"][k] = v

            step_template.append(step_tmpl)

        from .models import MacroInputContract, MacroOutputContract, MacroSafetyContract, MacroRollbackContract

        macro = WorkflowMacro(
            macro_id=f"{candidate.proposed_name}:{candidate.proposed_version}",
            name=candidate.proposed_name,
            version=candidate.proposed_version,
            source_fragment_id=candidate.source_fragment_id,
            description=f"Macro promoted from fragment {candidate.source_fragment_id}",
            step_template=step_template,
            input_contract=MacroInputContract(**candidate.contracts.get("input_contract", {})),
            output_contract=MacroOutputContract(**candidate.contracts.get("output_contract", {})),
            dependency_shape=fragment.dependency_shape,
            safety_contract=MacroSafetyContract(**candidate.contracts.get("safety_contract", {})),
            rollback_contract=MacroRollbackContract(**candidate.contracts.get("rollback_contract", {})),
            verification_status="pending"
        )

        self.library_manager.add_macro_version(macro)
        candidate.status = "adopted"
        self.promotion_engine._save_candidate(candidate)
        self.telemetry.emit("macro_promoted", {"macro_id": macro.macro_id})

        return macro

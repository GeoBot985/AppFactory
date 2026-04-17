import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from .models import (
    WorkflowMacro,
    MacroLibrary,
    MacroInputContract,
    MacroOutputContract,
    MacroSafetyContract,
    MacroRollbackContract
)

class MacroLibraryManager:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.macros_root = workspace_root / "runtime_data" / "macros"
        self.library_path = self.macros_root / "library.json"
        self.macros_dir = self.macros_root / "macros"

        self.macros_root.mkdir(parents=True, exist_ok=True)
        self.macros_dir.mkdir(parents=True, exist_ok=True)

    def load_library(self) -> MacroLibrary:
        if not self.library_path.exists():
            return MacroLibrary(library_id="default")

        with open(self.library_path, "r") as f:
            data = json.load(f)
            return MacroLibrary(
                library_id=data.get("library_id", "default"),
                active_versions=data.get("active_versions", {})
            )

    def save_library(self, library: MacroLibrary):
        data = {
            "library_id": library.library_id,
            "active_versions": library.active_versions
        }
        with open(self.library_path, "w") as f:
            json.dump(data, f, indent=2)

    def add_macro_version(self, macro: WorkflowMacro):
        macro_dir = self.macros_dir / macro.name / macro.version
        macro_dir.mkdir(parents=True, exist_ok=True)

        with open(macro_dir / "macro.json", "w") as f:
            json.dump(self._macro_to_dict(macro), f, indent=2)

        contracts = {
            "input": vars(macro.input_contract),
            "output": vars(macro.output_contract),
            "safety": vars(macro.safety_contract),
            "rollback": vars(macro.rollback_contract)
        }
        with open(macro_dir / "contracts.json", "w") as f:
            json.dump(contracts, f, indent=2)

    def get_macro(self, name: str, version: str) -> Optional[WorkflowMacro]:
        macro_file = self.macros_dir / name / version / "macro.json"
        if not macro_file.exists():
            return None

        with open(macro_file, "r") as f:
            data = json.load(f)

        contracts_file = self.macros_dir / name / version / "contracts.json"
        if contracts_file.exists():
            with open(contracts_file, "r") as f:
                c_data = json.load(f)
                data["input_contract"] = MacroInputContract(**c_data["input"])
                data["output_contract"] = MacroOutputContract(**c_data["output"])
                data["safety_contract"] = MacroSafetyContract(**c_data["safety"])
                data["rollback_contract"] = MacroRollbackContract(**c_data["rollback"])

        return WorkflowMacro(**data)

    def list_macros(self) -> List[WorkflowMacro]:
        macros = []
        if not self.macros_dir.exists():
            return []

        for name_dir in sorted(self.macros_dir.iterdir()):
            if not name_dir.is_dir(): continue
            for version_dir in sorted(name_dir.iterdir()):
                if not version_dir.is_dir(): continue
                macro = self.get_macro(name_dir.name, version_dir.name)
                if macro:
                    macros.append(macro)
        return macros

    def get_active_macro(self, name: str) -> Optional[WorkflowMacro]:
        library = self.load_library()
        version = library.active_versions.get(name)
        if not version:
            return None
        return self.get_macro(name, version)

    def _macro_to_dict(self, m: WorkflowMacro) -> Dict[str, Any]:
        return {
            "macro_id": m.macro_id,
            "name": m.name,
            "version": m.version,
            "source_fragment_id": m.source_fragment_id,
            "description": m.description,
            "step_template": m.step_template,
            "dependency_shape": m.dependency_shape,
            "verification_status": m.verification_status
        }

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from .models import SuggestionUsage, SuggestionEffectiveness

class SuggestionTracker:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.suggestions_dir = workspace_root / "runtime_data" / "suggestions"
        self.suggestions_dir.mkdir(parents=True, exist_ok=True)
        self.usage_file = self.suggestions_dir / "usage.json"
        self.effectiveness_file = self.suggestions_dir / "effectiveness.json"

    def record_usage(self, usage: SuggestionUsage):
        usages = self._load_usages()
        usages.append(usage.model_dump())
        self._save_usages(usages)
        self._update_effectiveness(usage)

    def get_effectiveness(self) -> List[SuggestionEffectiveness]:
        if not self.effectiveness_file.exists():
            return []
        with open(self.effectiveness_file, "r") as f:
            try:
                data = json.load(f)
                return [SuggestionEffectiveness(**item) for item in data]
            except:
                return []

    def _load_usages(self) -> List[Dict[str, Any]]:
        if not self.usage_file.exists():
            return []
        with open(self.usage_file, "r") as f:
            try:
                return json.load(f)
            except:
                return []

    def _save_usages(self, usages: List[Dict[str, Any]]):
        with open(self.usage_file, "w") as f:
            json.dump(usages, f, indent=2, default=str)

    def _update_effectiveness(self, usage: SuggestionUsage):
        eff_list = self.get_effectiveness()
        eff_map = {e.suggestion_id: e for e in eff_list}

        if usage.suggestion_id not in eff_map:
            eff_map[usage.suggestion_id] = SuggestionEffectiveness(suggestion_id=usage.suggestion_id)

        eff = eff_map[usage.suggestion_id]
        eff.usage_count += 1
        if usage.applied:
            eff.application_count += 1
        if usage.resolved_issue:
            eff.resolution_count += 1

        # For v1, avg_steps_to_resolution is placeholder or could be updated if passed in usage

        self._save_effectiveness(list(eff_map.values()))

    def _save_effectiveness(self, eff_list: List[SuggestionEffectiveness]):
        with open(self.effectiveness_file, "w") as f:
            json.dump([e.model_dump() for e in eff_list], f, indent=2)

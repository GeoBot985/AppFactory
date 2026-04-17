import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from .models import KnowledgeEntry, PatternSolution, KnowledgeBaseData

class KnowledgeStore:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.kb_dir = workspace_root / "runtime_data" / "knowledge"
        self.kb_dir.mkdir(parents=True, exist_ok=True)

        self.entries_file = self.kb_dir / "knowledge_entries.json"
        self.mappings_file = self.kb_dir / "pattern_solutions.json"
        self.metrics_file = self.kb_dir / "metrics.json"

    def load_kb(self) -> KnowledgeBaseData:
        entries = self._load_json(self.entries_file)
        mappings = self._load_json(self.mappings_file)

        return KnowledgeBaseData(
            entries=[KnowledgeEntry(**e) for e in entries],
            mappings={k: PatternSolution(**v) for k, v in mappings.items()}
        )

    def save_kb(self, kb: KnowledgeBaseData):
        self._save_json(self.entries_file, [e.model_dump() for e in kb.entries])
        self._save_json(self.mappings_file, {k: v.model_dump() for k, v in kb.mappings.items()})

        # Aggregate metrics for metrics.json
        metrics = self._calculate_metrics(kb)
        self._save_json(self.metrics_file, metrics)

    def _load_json(self, path: Path) -> List | Dict:
        if not path.exists():
            return [] if "entries" in path.name else {}
        with open(path, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return [] if "entries" in path.name else {}

    def _save_json(self, path: Path, data: List | Dict):
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _calculate_metrics(self, kb: KnowledgeBaseData) -> Dict:
        total_entries = len(kb.entries)
        total_usage = sum(e.usage_count for e in kb.entries)
        total_success = sum(e.success_count for e in kb.entries)

        return {
            "total_entries": total_entries,
            "total_usage": total_usage,
            "total_success": total_success,
            "overall_success_rate": total_success / max(total_usage, 1),
            "last_updated": str(datetime.now())
        }

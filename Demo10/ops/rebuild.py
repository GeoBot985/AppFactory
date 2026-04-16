from pathlib import Path
from .ops_service import OpsService
from .health import HealthEvaluator

class RebuildService:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.ops_service = OpsService(project_root)
        self.health_evaluator = HealthEvaluator(project_root)

    def rebuild_all(self):
        print("Rebuilding all ops indices...")
        self.ops_service.rebuild_all_indices()
        print("Evaluating system health...")
        self.health_evaluator.evaluate()
        print("Rebuild complete.")

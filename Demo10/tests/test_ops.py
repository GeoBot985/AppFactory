import unittest
from pathlib import Path
import json
import shutil
import os
from Demo10.ops.ops_service import OpsService
from Demo10.ops.models import DashboardSummary

class TestOpsService(unittest.TestCase):
    def setUp(self):
        self.test_root = Path("test_ops_root")
        if self.test_root.exists():
            shutil.rmtree(self.test_root)
        self.test_root.mkdir()
        self.ops_service = OpsService(self.test_root)

    def tearDown(self):
        if self.test_root.exists():
            shutil.rmtree(self.test_root)

    def test_rebuild_dashboard_summary_empty(self):
        self.ops_service.rebuild_dashboard_summary()
        summary_file = self.test_root / "runtime_data" / "ops" / "dashboard_summary.json"
        self.assertTrue(summary_file.exists())
        with summary_file.open("r") as f:
            data = json.load(f)
            self.assertEqual(data["active_queues"], 0)

if __name__ == "__main__":
    unittest.main()

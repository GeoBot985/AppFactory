import unittest
from pathlib import Path
import json
import shutil
import os
from metrics.models import RunMetrics, TaskMetrics, StageMetrics, ModelUsage
from metrics.metrics_service import MetricsService

class TestSpec032Metrics(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("test_metrics_run")
        self.test_dir.mkdir(exist_ok=True)
        self.metrics_service = MetricsService(self.test_dir)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_run_metrics_lifecycle(self):
        self.metrics_service.start_run("test_run_1")
        self.metrics_service.start_high_level_stage("compile")
        self.metrics_service.end_high_level_stage("compile")

        tm = self.metrics_service.get_task_metrics("task_1", "GENERATE_FILE")
        self.metrics_service.start_task("task_1", "GENERATE_FILE")
        tm.attempts = 1
        self.metrics_service.record_model_usage("task_1", "llama3", 500.0, True, 100)
        self.metrics_service.end_task("task_1")

        self.metrics_service.end_run()

        metrics_file = self.test_dir / "metrics" / "run_metrics.json"
        self.assertTrue(metrics_file.exists())

        with metrics_file.open("r") as f:
            data = json.load(f)
            self.assertEqual(data["run_id"], "test_run_1")
            self.assertEqual(data["total_attempts"], 1)
            self.assertEqual(data["total_model_calls"], 1)
            self.assertIn("compile", data["high_level_stages"])
            self.assertIn("task_1", data["tasks"])

    def test_slow_step_detection(self):
        self.metrics_service.start_run("test_run_slow")
        tm = self.metrics_service.get_task_metrics("slow_task", "GENERATE_FILE")
        self.metrics_service.start_task("slow_task", "GENERATE_FILE")
        # Gen latency threshold is 30s
        self.metrics_service.record_model_usage("slow_task", "llama3", 35000.0, True)
        self.metrics_service.end_task("slow_task")

        self.assertTrue(tm.slow_step)
        self.assertEqual(tm.slow_reason, "generation_latency_high")

    def test_anomaly_detection(self):
        self.metrics_service.start_run("test_run_anomaly")
        tm = self.metrics_service.get_task_metrics("retry_task", "GENERATE_FILE")
        self.metrics_service.start_task("retry_task", "GENERATE_FILE")
        tm.attempts = 5
        self.metrics_service.end_task("retry_task")

        self.assertIn("too_many_retries", tm.anomaly_flags)

if __name__ == "__main__":
    unittest.main()

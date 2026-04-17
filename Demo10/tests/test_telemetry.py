import unittest
from pathlib import Path
import shutil
import os
from datetime import date
from telemetry.events import TelemetryEmitter
from telemetry.aggregator import TelemetryAggregator
from telemetry.query import TelemetryQuery
from telemetry.alerts import TelemetryAlerts
from services.execution.engine import ExecutionEngine
from services.planner.models import ExecutionPlan, Step, StepContract

class TestTelemetry(unittest.TestCase):
    def setUp(self):
        self.workspace_root = Path("test_telemetry_ws")
        if self.workspace_root.exists():
            shutil.rmtree(self.workspace_root)
        self.workspace_root.mkdir()

    def tearDown(self):
        if self.workspace_root.exists():
            shutil.rmtree(self.workspace_root)

    def test_event_emission_and_aggregation(self):
        emitter = TelemetryEmitter(self.workspace_root)
        emitter.emit("run_started", {"run_id": "run_1", "plan_id": "plan_1"})
        emitter.emit("step_started", {"run_id": "run_1", "step_id": "step_1", "step_type": "create_file"})
        emitter.emit("step_completed", {"run_id": "run_1", "step_id": "step_1", "step_type": "create_file", "attempts": 1, "duration_ms": 100})
        emitter.emit("run_completed", {"run_id": "run_1", "status": "completed", "duration_ms": 500})

        aggregator = TelemetryAggregator(self.workspace_root)
        agg = aggregator.aggregate_day(date.today())

        self.assertEqual(agg.runs_total, 1)
        self.assertEqual(agg.runs_completed, 1)
        self.assertEqual(agg.steps_total, 1)
        self.assertEqual(agg.failure_rate, 0.0)

    def test_retry_metrics(self):
        emitter = TelemetryEmitter(self.workspace_root)
        emitter.emit("run_started", {"run_id": "run_2", "plan_id": "plan_2"})
        emitter.emit("step_started", {"run_id": "run_2", "step_id": "step_2", "step_type": "create_file"})
        emitter.emit("step_failed", {"run_id": "run_2", "step_id": "step_2", "step_type": "create_file", "error_code": "ERROR", "attempt_index": 1, "classification": "retryable"})
        emitter.emit("retry_attempt", {"run_id": "run_2", "step_id": "step_2", "attempt_index": 2, "delay_ms": 100})
        emitter.emit("step_completed", {"run_id": "run_2", "step_id": "step_2", "step_type": "create_file", "attempts": 2, "duration_ms": 200})
        emitter.emit("run_completed", {"run_id": "run_2", "status": "completed", "duration_ms": 600})

        aggregator = TelemetryAggregator(self.workspace_root)
        agg = aggregator.aggregate_day(date.today())

        self.assertEqual(agg.retries_total, 1)
        self.assertEqual(agg.steps_recovered_via_retry, 1)
        self.assertEqual(agg.retry_success_rate, 1.0)

    def test_alerts(self):
        aggregator = TelemetryAggregator(self.workspace_root)
        # Manually create a failing aggregate
        agg = aggregator.aggregate_day(date.today())
        agg.runs_total = 10
        agg.runs_failed = 5
        agg.failure_rate = 0.5

        alerts_service = TelemetryAlerts(self.workspace_root)
        triggered = alerts_service.evaluate_rules(agg)

        self.assertTrue(any(a.rule == "failure_rate_critical" for a in triggered))

if __name__ == "__main__":
    unittest.main()

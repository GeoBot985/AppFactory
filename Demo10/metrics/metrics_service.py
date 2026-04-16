from __future__ import annotations
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any
from .models import RunMetrics, TaskMetrics, StageMetrics, ModelUsage, RunSummary

class MetricsService:
    def __init__(self, run_folder: Optional[Path] = None):
        self.run_folder = run_folder
        self.current_run: Optional[RunMetrics] = None

    def start_run(self, run_id: str):
        if self.current_run and self.current_run.run_id == run_id:
            return
        self.current_run = RunMetrics(
            run_id=run_id,
            started_at=self._now()
        )

    def record_template_usage(self, template_id: str, version: int):
        if not self.current_run:
            return
        self.current_run.metadata["template_id"] = template_id
        self.current_run.metadata["template_version"] = version

    def end_run(self):
        if not self.current_run:
            return
        self.current_run.completed_at = self._now()
        self.current_run.total_duration_ms = self._calc_duration(self.current_run.started_at, self.current_run.completed_at)
        self._aggregate_run_metrics()
        self.save_metrics()

    def start_high_level_stage(self, stage_name: str):
        if not self.current_run:
            return
        stage = StageMetrics(stage_name=stage_name, started_at=self._now())
        self.current_run.high_level_stages[stage_name] = stage

    def end_high_level_stage(self, stage_name: str, success: bool = True, error: Optional[str] = None):
        if not self.current_run or stage_name not in self.current_run.high_level_stages:
            return
        stage = self.current_run.high_level_stages[stage_name]
        stage.completed_at = self._now()
        stage.duration_ms = self._calc_duration(stage.started_at, stage.completed_at)
        stage.success = success
        stage.error = error

    def get_task_metrics(self, task_id: str, task_type: str = "unknown") -> TaskMetrics:
        if not self.current_run:
            # Fallback for when we don't have a run context (e.g. tests)
            return TaskMetrics(task_id=task_id, task_type=task_type)

        if task_id not in self.current_run.tasks:
            self.current_run.tasks[task_id] = TaskMetrics(task_id=task_id, task_type=task_type)
        return self.current_run.tasks[task_id]

    def start_task(self, task_id: str, task_type: str):
        metrics = self.get_task_metrics(task_id, task_type)
        metrics.started_at = self._now()

    def start_internal_stage(self, task_id: str, stage_name: str):
        metrics = self.get_task_metrics(task_id)
        stage = StageMetrics(stage_name=stage_name, started_at=self._now())
        metrics.stages[stage_name] = stage

    def end_internal_stage(self, task_id: str, stage_name: str, success: bool = True, error: Optional[str] = None):
        metrics = self.get_task_metrics(task_id)
        if stage_name not in metrics.stages:
            return
        stage = metrics.stages[stage_name]
        stage.completed_at = self._now()
        stage.duration_ms = self._calc_duration(stage.started_at, stage.completed_at)
        stage.success = success
        stage.error = error

    def end_task(self, task_id: str):
        if not self.current_run or task_id not in self.current_run.tasks:
            return
        metrics = self.current_run.tasks[task_id]
        metrics.completed_at = self._now()
        metrics.duration_ms = self._calc_duration(metrics.started_at, metrics.completed_at)
        self._check_slow_step(metrics)

    def record_model_usage(self, task_id: str, model_name: str, latency_ms: float, success: bool, tokens: Optional[int] = None):
        metrics = self.get_task_metrics(task_id)
        if model_name not in metrics.model_usage:
            metrics.model_usage[model_name] = ModelUsage(model_name=model_name)

        usage = metrics.model_usage[model_name]
        usage.call_count += 1
        usage.total_latency_ms += latency_ms
        if success:
            usage.success_count += 1
        else:
            usage.failure_count += 1
        if tokens:
            if usage.total_tokens is None: usage.total_tokens = 0
            usage.total_tokens += tokens

    def _aggregate_run_metrics(self):
        if not self.current_run:
            return

        total_attempts = 0
        total_model_calls = 0
        total_gen_latency = 0.0
        total_files = 0
        total_added = 0
        total_removed = 0

        for task in self.current_run.tasks.values():
            total_attempts += task.attempts
            for usage in task.model_usage.values():
                total_model_calls += usage.call_count
                total_gen_latency += usage.total_latency_ms
            total_files += task.files_changed
            total_added += task.lines_added
            total_removed += task.lines_removed

        self.current_run.total_attempts = total_attempts
        self.current_run.total_model_calls = total_model_calls
        if total_model_calls > 0:
            self.current_run.avg_generation_latency_ms = total_gen_latency / total_model_calls
        self.current_run.total_files_changed = total_files
        self.current_run.total_lines_added = total_added
        self.current_run.total_lines_removed = total_removed

    def create_summary(self, risk_level: str = "unknown") -> RunSummary:
        if not self.current_run:
            return RunSummary("none", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, risk_level)

        tasks_executed = len(self.current_run.tasks)
        tasks_failed = sum(1 for t in self.current_run.tasks.values() if t.failure_class)

        tests_run = 0
        tests_passed = 0
        tests_failed = 0
        for task in self.current_run.tasks.values():
            if task.task_type == "RUN_TESTS":
                # This logic depends on how we store test results in TaskMetrics
                # For now, let's assume we can derive it or it's recorded in metadata
                tests_run += 1 # placeholder
                if task.test_failures == 0:
                    tests_passed += 1
                else:
                    tests_failed += 1

        return RunSummary(
            run_id=self.current_run.run_id,
            total_duration_ms=self.current_run.total_duration_ms,
            tasks_executed=tasks_executed,
            tasks_failed=tasks_failed,
            retry_count=self.current_run.total_attempts - tasks_executed if self.current_run.total_attempts > tasks_executed else 0,
            model_calls=self.current_run.total_model_calls,
            avg_generation_latency_ms=self.current_run.avg_generation_latency_ms,
            tests_run=tests_run,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            files_changed=self.current_run.total_files_changed,
            risk_level=risk_level
        )

    def save_metrics(self):
        if not self.run_folder or not self.current_run:
            return

        metrics_dir = self.run_folder / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)

        # Save full metrics
        with (metrics_dir / "run_metrics.json").open("w") as f:
            json.dump(self.current_run.to_dict(), f, indent=2)

        # Save summary
        summary = self.create_summary()
        with (metrics_dir / "run_summary.json").open("w") as f:
            json.dump(summary.to_dict(), f, indent=2)

    def _now(self) -> str:
        return datetime.now().isoformat()

    def _calc_duration(self, start: Optional[str], end: Optional[str]) -> float:
        if not start or not end:
            return 0.0
        try:
            d1 = datetime.fromisoformat(start)
            d2 = datetime.fromisoformat(end)
            return (d2 - d1).total_seconds() * 1000.0
        except:
            return 0.0

    def _check_slow_step(self, metrics: TaskMetrics):
        # Thresholds (Spec 032 requirement 10)
        GEN_LATENCY_THRESHOLD = 30000 # 30s
        TEST_DURATION_THRESHOLD = 60000 # 60s
        RETRY_THRESHOLD = 3

        if metrics.task_type in ["GENERATE_FILE", "GENERATE_PATCH", "CREATE", "MODIFY"]:
            for usage in metrics.model_usage.values():
                if usage.call_count > 0 and (usage.total_latency_ms / usage.call_count) > GEN_LATENCY_THRESHOLD:
                    metrics.slow_step = True
                    metrics.slow_reason = "generation_latency_high"

        if metrics.task_type == "RUN_TESTS" and metrics.duration_ms > TEST_DURATION_THRESHOLD:
            metrics.slow_step = True
            metrics.slow_reason = "tests_duration_high"

        if metrics.attempts > RETRY_THRESHOLD:
            metrics.anomaly_flags.append("too_many_retries")

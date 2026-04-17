import json
import os
from pathlib import Path
from datetime import datetime, date
import statistics
from typing import List, Dict, Any, Optional
from .models import TelemetryEvent, Metric, DailyAggregate
from diagnostics.patterns import PatternManager
from diagnostics.reports import DiagnosticsReporter

class TelemetryAggregator:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.telemetry_dir = workspace_root / "runtime_data" / "telemetry"
        self.events_dir = self.telemetry_dir / "events"
        self.metrics_dir = self.telemetry_dir / "metrics"
        self.aggregates_dir = self.telemetry_dir / "aggregates"

        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        self.aggregates_dir.mkdir(parents=True, exist_ok=True)

        self.pattern_manager = PatternManager(workspace_root)
        self.reporter = DiagnosticsReporter(workspace_root)

    def aggregate_day(self, target_date: date) -> DailyAggregate:
        date_str = target_date.strftime("%Y-%m-%d")
        event_file = self.events_dir / f"{date_str}.jsonl"

        agg = DailyAggregate(date=date_str)

        if not event_file.exists():
            return agg

        events = []
        with open(event_file, "r") as f:
            for line in f:
                try:
                    event = TelemetryEvent.model_validate_json(line)
                    events.append(event)
                    # Process for diagnostics
                    self.pattern_manager.process_failure(event)
                except Exception:
                    continue

        # Basic counts
        agg.runs_total = sum(1 for e in events if e.event_type == "run_started")

        completed_runs = [e for e in events if e.event_type == "run_completed"]
        agg.runs_completed = sum(1 for e in completed_runs if e.payload.get("status") == "completed")
        agg.runs_failed = sum(1 for e in completed_runs if e.payload.get("status") == "failed")

        # Partial failure: failed run but with clean or partially restored outcome
        agg.runs_partial_failure = sum(1 for e in completed_runs if e.payload.get("status") == "failed" and e.payload.get("consistency_outcome") in ["clean", "partially_restored"])

        if agg.runs_total > 0:
            agg.failure_rate = agg.runs_failed / (agg.runs_completed + agg.runs_failed) if (agg.runs_completed + agg.runs_failed) > 0 else 0

        agg.steps_total = sum(1 for e in events if e.event_type == "step_started")
        agg.steps_failed = sum(1 for e in events if e.event_type == "step_failed" and e.payload.get("is_terminal"))

        # steps_recovered_via_retry is more complex to find from events alone without state.
        # But step_completed payload has "attempts". If attempts > 1, it's recovered.
        completed_steps = [e for e in events if e.event_type == "step_completed"]
        agg.steps_recovered_via_retry = sum(1 for e in completed_steps if e.payload.get("attempts", 1) > 1)

        agg.retries_total = sum(1 for e in events if e.event_type == "retry_attempt")

        if (agg.steps_failed + agg.steps_recovered_via_retry) > 0:
            agg.retry_success_rate = agg.steps_recovered_via_retry / (agg.steps_failed + agg.steps_recovered_via_retry)

        agg.rollback_invocations = sum(1 for e in events if e.event_type == "rollback_started")
        rollback_completions = [e for e in events if e.event_type == "rollback_completed"]
        rollback_successes = sum(1 for e in rollback_completions if e.payload.get("status") == "completed")
        if agg.rollback_invocations > 0:
            agg.rollback_success_rate = rollback_successes / agg.rollback_invocations

        # Verification
        agg.verification_runs_total = sum(1 for e in events if e.event_type == "verification_run")
        v_results = [e for e in events if e.event_type == "verification_result"]
        agg.verification_pass = sum(1 for e in v_results if e.payload.get("overall_verdict") == "pass")
        agg.verification_warn = sum(1 for e in v_results if e.payload.get("overall_verdict") == "pass_with_warnings")
        agg.verification_fail = sum(1 for e in v_results if e.payload.get("overall_verdict") == "fail")
        agg.drift_events_total = sum(e.payload.get("drift_events", 0) for e in v_results)

        # Promotion
        p_decisions = [e for e in events if e.event_type == "promotion_decision"]
        agg.promotions_attempted = len(p_decisions)
        agg.promotions_approved = sum(1 for e in p_decisions if "approved" in e.payload.get("decision", ""))
        agg.promotions_rejected = sum(1 for e in p_decisions if e.payload.get("decision") == "rejected")
        agg.promotions_overridden = sum(1 for e in p_decisions if e.payload.get("is_override"))

        # Durations
        run_durations = [e.payload.get("duration_ms", 0) for e in completed_runs if "duration_ms" in e.payload]
        if run_durations:
            agg.run_duration_p50_ms = statistics.median(run_durations)
            agg.run_duration_p95_ms = sorted(run_durations)[int(len(run_durations) * 0.95)]

        step_durations = [e.payload.get("duration_ms", 0) for e in completed_steps if "duration_ms" in e.payload]
        if step_durations:
            agg.step_duration_p50_ms = statistics.median(step_durations)
            agg.step_duration_p95_ms = sorted(step_durations)[int(len(step_durations) * 0.95)]

        # Derived
        if agg.verification_runs_total > 0:
            agg.stability_score = agg.verification_pass / agg.verification_runs_total
            agg.drift_rate = agg.drift_events_total / agg.verification_runs_total

        agg.reliability_index = (1 - agg.failure_rate) * agg.retry_success_rate if agg.retry_success_rate > 0 else (1 - agg.failure_rate)

        self._store_aggregate(agg)
        self.reporter.generate_daily_report(target_date)
        self._generate_metrics(agg, target_date)

        return agg

    def _store_aggregate(self, agg: DailyAggregate):
        file_path = self.aggregates_dir / "daily_summary.json"

        # We store daily summaries in a dict keyed by date
        summaries = {}
        if file_path.exists():
            with open(file_path, "r") as f:
                summaries = json.load(f)

        summaries[agg.date] = agg.model_dump()

        with open(file_path, "w") as f:
            json.dump(summaries, f, indent=2)

    def _generate_metrics(self, agg: DailyAggregate, target_date: date):
        date_str = target_date.strftime("%Y-%m-%d")
        file_path = self.metrics_dir / f"{date_str}.jsonl"

        # Convert agg fields to Metric objects
        metrics = []
        for field, value in agg.model_dump().items():
            if field == "date": continue
            if isinstance(value, (int, float)):
                m = Metric(
                    name=field,
                    type="gauge" if "rate" in field or "index" in field or "score" in field else "counter",
                    value=float(value),
                    labels={"date": agg.date},
                    timestamp=datetime.combine(target_date, datetime.min.time())
                )
                metrics.append(m)

        with open(file_path, "w") as f:
            for m in metrics:
                f.write(m.model_dump_json() + "\n")

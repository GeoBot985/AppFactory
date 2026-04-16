import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from .models import (
    DashboardSummary, QueueIndexEntry, RunIndexEntry,
    ApprovalIndexEntry, RegressionIndexEntry, RecoveryIndexEntry,
    RuntimeProfileIndexEntry, TrendData
)

class OpsService:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.ops_dir = project_root / "runtime_data" / "ops"
        self.ops_dir.mkdir(parents=True, exist_ok=True)

        self.ledger_dir = project_root / "runtime_data" / "run_ledger"
        self.queues_dir = project_root / "runtime_data" / "queues"
        self.approvals_file = project_root / "runtime_data" / "policy" / "approvals.json"

    def _save_index(self, filename: str, data: Any):
        filepath = self.ops_dir / filename
        temp_file = filepath.with_suffix(".tmp")
        with temp_file.open("w") as f:
            if isinstance(data, list):
                json.dump([item.to_dict() if hasattr(item, "to_dict") else item for item in data], f, indent=2)
            elif hasattr(data, "to_dict"):
                json.dump(data.to_dict(), f, indent=2)
            else:
                json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        temp_file.replace(filepath)

    def rebuild_all_indices(self):
        # This will be called by RebuildService or directly
        self.rebuild_queue_index()
        self.rebuild_run_index()
        self.rebuild_approval_index()
        self.rebuild_regression_index()
        self.rebuild_recovery_index()
        self.rebuild_trends()
        self.rebuild_dashboard_summary()

    def rebuild_queue_index(self):
        queue_index = []
        current_queues_file = self.ledger_dir / "current_queues.json"
        if current_queues_file.exists():
            with current_queues_file.open("r") as f:
                current_queues = json.load(f)

            for queue_id in current_queues:
                q_def_file = self.queues_dir / f"{queue_id}.json"
                if q_def_file.exists():
                    with q_def_file.open("r") as f:
                        q_data = json.load(f)

                    slots = q_data.get("slots", [])
                    completed = sum(1 for s in slots if s.get("state") in ["COMPLETED", "COMPLETED_WITH_WARNINGS"])
                    failed = sum(1 for s in slots if s.get("state") in ["FAILED", "PARTIAL_FAILURE"])
                    approval_pending = sum(1 for s in slots if s.get("state") == "APPROVAL_REQUIRED") # Adjust based on actual state names

                    created_at = q_data.get("created_at", datetime.now().isoformat())
                    try:
                        created_dt = datetime.fromisoformat(created_at)
                        age_minutes = int((datetime.now() - created_dt).total_seconds() / 60)
                    except:
                        age_minutes = 0

                    entry = QueueIndexEntry(
                        queue_id=queue_id,
                        status=q_data.get("state", "UNKNOWN"),
                        source_policy=q_data.get("source_policy", "unknown"),
                        runtime_profile_default=q_data.get("runtime_defaults", {}).get("profile", "unknown"),
                        slots_total=len(slots),
                        slots_completed=completed,
                        slots_failed=failed,
                        slots_pending=len(slots) - completed - failed,
                        slots_approval_pending=approval_pending,
                        current_slot_id=None, # TBD from active queue state
                        created_at=created_at,
                        updated_at=q_data.get("updated_at", created_at),
                        age_minutes=age_minutes
                    )
                    queue_index.append(entry)

        self._save_index("queue_index.json", queue_index)

    def rebuild_run_index(self):
        run_index = []
        current_runs_file = self.ledger_dir / "current_runs.json"
        if current_runs_file.exists():
            with current_runs_file.open("r") as f:
                current_runs = json.load(f)

            for run_id, run_data in current_runs.items():
                started_at = run_data.get("created_at", datetime.now().isoformat())
                updated_at = run_data.get("updated_at", started_at)

                duration = None
                try:
                    start_dt = datetime.fromisoformat(started_at)
                    end_dt = datetime.fromisoformat(updated_at)
                    duration = (end_dt - start_dt).total_seconds()
                except:
                    pass

                entry = RunIndexEntry(
                    run_id=run_id,
                    queue_id=run_data.get("queue_id", ""),
                    slot_id=run_data.get("slot_id", ""),
                    spec_id=run_data.get("spec_id", ""),
                    state=run_data.get("state", "UNKNOWN"),
                    final_status=None, # Derived if completed
                    failure_stage=None, # TBD
                    risk_class=None, # TBD from risk assessment artifact
                    policy_status=None,
                    approval_status=None,
                    promotion_status=None,
                    runtime_profile=run_data.get("runtime_profile", "unknown"),
                    started_at=started_at,
                    duration_seconds=duration,
                    last_phase=run_data.get("state"),
                    resumable_classification=None
                )
                run_index.append(entry)

        self._save_index("run_index.json", run_index)

    def rebuild_approval_index(self):
        approval_index = []
        if self.approvals_file.exists():
            with self.approvals_file.open("r") as f:
                approvals = json.load(f)

            for app_id, app_data in approvals.items():
                req_at = app_data.get("requested_at", datetime.now().isoformat())
                try:
                    req_dt = datetime.fromisoformat(req_at)
                    age_minutes = int((datetime.now() - req_dt).total_seconds() / 60)
                except:
                    age_minutes = 0

                entry = ApprovalIndexEntry(
                    approval_id=app_id,
                    gate_type=app_data.get("gate_type", "unknown"),
                    entity_type=app_data.get("entity_type", "unknown"),
                    entity_id=app_data.get("entity_id", "unknown"),
                    queue_id=app_data.get("queue_id", ""),
                    slot_id=app_data.get("slot_id", ""),
                    risk_class=app_data.get("risk_class", "R0_LOW"),
                    reason_codes=app_data.get("reason_codes", []),
                    status=app_data.get("status", "PENDING"),
                    requested_at=req_at,
                    age_minutes=age_minutes,
                    decider=app_data.get("decider"),
                    decided_at=app_data.get("decided_at")
                )
                approval_index.append(entry)

        self._save_index("approval_index.json", approval_index)

    def rebuild_regression_index(self):
        regression_index = []
        regression_runs_root = self.project_root / "regression_runs"
        if regression_runs_root.exists():
            # Get latest run directory
            run_dirs = sorted([d for d in regression_runs_root.iterdir() if d.is_dir()], reverse=True)
            if run_dirs:
                latest_run_dir = run_dirs[0]
                summary_file = latest_run_dir / "summary.json"
                if summary_file.exists():
                    with summary_file.open("r") as f:
                        summary = json.load(f)

                    # Extract suite status from summary
                    # Note: SPEC 018 wants suite_id, runtime_profile, etc.
                    # We'll map what we have.
                    entry = RegressionIndexEntry(
                        suite_id=summary.get("suite", "unknown"),
                        runtime_profile="unknown", # TBD
                        last_run_at=summary.get("timestamp", ""),
                        last_status="PASS" if summary.get("failed", 0) == 0 else "FAIL",
                        passing_cases=summary.get("passed", 0),
                        failing_cases=summary.get("failed", 0),
                        warning_cases=0,
                        environment_baseline_match_status="OK",
                        update_baseline_history=[]
                    )
                    regression_index.append(entry)

        self._save_index("regression_index.json", regression_index)

    def rebuild_recovery_index(self):
        recovery_index = []
        from Demo10.services.run_ledger.ledger import LedgerService
        from Demo10.services.run_ledger.recovery import RecoveryService
        ledger = LedgerService(self.project_root)
        recovery_service = RecoveryService(self.project_root, ledger)
        plan = recovery_service.scan_for_interrupted_runs()

        for item in plan:
            metadata = ledger.get_run_metadata(item.run_id)
            entry = RecoveryIndexEntry(
                run_id=item.run_id,
                queue_id=metadata.queue_id if metadata else "unknown",
                last_durable_state=metadata.state.value if metadata else "unknown",
                classification=item.category.value,
                action_options=[item.recommended_action.value],
                artifact_integrity="OK" # Simplified
            )
            recovery_index.append(entry)

        self._save_index("recovery_index.json", recovery_index)

    def rebuild_trends(self):
        # Very simple trend: counts from current indices
        run_index = self._load_json("run_index.json", [])
        approval_index = self._load_json("approval_index.json", [])
        regression_index = self._load_json("regression_index.json", [])

        status_counts = {}
        for r in run_index:
            s = r.get("state", "UNKNOWN")
            status_counts[s] = status_counts.get(s, 0) + 1

        appr_counts = {}
        for a in approval_index:
            s = a.get("status", "PENDING")
            appr_counts[s] = appr_counts.get(s, 0) + 1

        reg_counts = {}
        for reg in regression_index:
            s = reg.get("last_status", "UNKNOWN")
            reg_counts[s] = reg_counts.get(s, 0) + 1

        trend = TrendData(
            timestamp=datetime.now().isoformat(),
            runs_by_status=status_counts,
            failures_by_stage={},
            approvals_by_decision=appr_counts,
            regressions_by_status=reg_counts
        )
        self._save_index("trends.json", trend)

    def rebuild_dashboard_summary(self):
        # Load indices first
        queue_index = self._load_json("queue_index.json", [])
        run_index = self._load_json("run_index.json", [])
        approval_index = self._load_json("approval_index.json", [])
        regression_index = self._load_json("regression_index.json", [])

        summary = DashboardSummary(
            active_queues=sum(1 for q in queue_index if q.get("status") == "RUNNING"),
            paused_queues=sum(1 for q in queue_index if q.get("status") == "PAUSED"),
            running_runs=sum(1 for r in run_index if r.get("state") == "EXECUTING"),
            approval_pending_runs=sum(1 for a in approval_index if a.get("status") == "PENDING"),
            failing_regression_suites=sum(1 for reg in regression_index if reg.get("last_status") == "FAIL"),
            interrupted_runs=len(self._load_json("recovery_index.json", [])),
            ledger_issues=0 # TBD
        )

        self._save_index("dashboard_summary.json", summary)

    def _load_json(self, filename: str, default: Any) -> Any:
        filepath = self.ops_dir / filename
        if not filepath.exists():
            return default
        try:
            with filepath.open("r") as f:
                return json.load(f)
        except:
            return default

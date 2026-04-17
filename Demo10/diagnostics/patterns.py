import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from .models import FailureInstance, FailurePattern, RootCause
from .signature import generate_signature
from .classifier import classify_failure
from telemetry.models import TelemetryEvent, Alert
from pathlib import Path
import json

class PatternManager:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.telemetry_dir = workspace_root / "runtime_data" / "telemetry"
        self.alerts_dir = self.telemetry_dir / "alerts"
        self.diagnostics_dir = workspace_root / "runtime_data" / "diagnostics"
        self.instances_path = self.diagnostics_dir / "instances.json"
        self.patterns_path = self.diagnostics_dir / "patterns.json"
        self.signatures_path = self.diagnostics_dir / "signatures.json"
        self.root_causes_path = self.diagnostics_dir / "root_causes.json"
        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)

    def process_failure(self, event: TelemetryEvent):
        if event.event_type not in ["step_failed", "run_completed", "promotion_decision", "verification_result"]:
            # For step_completed, we only care if it recovered
            if event.event_type == "step_completed":
                if event.payload.get("attempts", 1) <= 1:
                    return
            else:
                return

        # Special check for run_completed: only if status is failed
        if event.event_type == "run_completed" and event.payload.get("status") != "failed":
            return

        error_code = event.payload.get("error_code")
        if not error_code and event.event_type == "run_completed":
            # If run failed, we usually want to wait for step_failed events for specific causes,
            # but we can track the run failure itself if no error code provided?
            # Actually, engine.py emits run_completed with status "failed" but maybe no error_code.
            # Usually we want the atomic failures.
            return

        if not error_code:
            error_code = "UNKNOWN_ERROR"

        root_cause = classify_failure(event)

        signature = generate_signature(
            error_code=error_code,
            step_type=event.payload.get("step_type", "unknown"),
            target=event.payload.get("target"),
            operation_type=event.payload.get("operation_type")
        )

        instance = FailureInstance(
            run_id=event.payload.get("run_id", "unknown"),
            step_id=event.payload.get("step_id"),
            error_code=error_code,
            signature_id=signature.signature_id,
            root_cause_id=root_cause.root_cause_id,
            timestamp=event.timestamp
        )

        self._store_instance(instance)
        self._update_pattern(instance, signature, root_cause)

    def _store_instance(self, instance: FailureInstance):
        instances = []
        if self.instances_path.exists():
            try:
                with open(self.instances_path, "r") as f:
                    instances = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        instances.append(instance.model_dump(mode="json"))

        # Keep only last 1000 instances to avoid bloat
        if len(instances) > 1000:
            instances = instances[-1000:]

        with open(self.instances_path, "w") as f:
            json.dump(instances, f, indent=2)

    def _update_pattern(self, instance: FailureInstance, signature, root_cause: RootCause):
        patterns = {}
        if self.patterns_path.exists():
            try:
                with open(self.patterns_path, "r") as f:
                    data = json.load(f)
                    patterns = {p["pattern_id"]: FailurePattern(**p) for p in data}
            except (json.JSONDecodeError, IOError):
                pass

        # Update standalone signatures
        self._store_signature(signature)
        # Update standalone root causes
        self._store_root_cause(root_cause)

        pattern_id = signature.signature_id
        if pattern_id in patterns:
            pattern = patterns[pattern_id]
            pattern.occurrences += 1
            pattern.last_seen = instance.timestamp
            if instance.run_id not in pattern.affected_runs:
                pattern.affected_runs.append(instance.run_id)
        else:
            pattern = FailurePattern(
                pattern_id=pattern_id,
                signature_id=signature.signature_id,
                error_code=instance.error_code,
                root_cause_id=instance.root_cause_id,
                occurrences=1,
                first_seen=instance.timestamp,
                last_seen=instance.timestamp,
                affected_runs=[instance.run_id]
            )
            patterns[pattern_id] = pattern

        # Update impact score
        # impact_score = frequency_weight * occurrences + severity_weight * severity + recency_weight * time_decay
        # v1 Weights: frequency=1.0, severity=5.0 (constant for failures), recency=1.0
        # Time decay omitted for initial v1 simplicity as per "keep weights fixed".

        pattern.impact_score = float(1.0 * pattern.occurrences + 5.0)

        with open(self.patterns_path, "w") as f:
            json.dump([p.model_dump(mode="json") for p in patterns.values()], f, indent=2)

        self._check_for_alerts(pattern, instance)

    def _check_for_alerts(self, pattern: FailurePattern, instance: FailureInstance):
        # Alert Integration (SPEC 052 Point 10)
        # High-frequency pattern -> alert
        if pattern.occurrences == 5 or pattern.occurrences == 10 or pattern.occurrences % 20 == 0:
            self._emit_alert(
                rule="high_frequency_failure_pattern",
                severity="warning",
                value=float(pattern.occurrences),
                message=f"High frequency failure pattern detected: {pattern.error_code} ({pattern.occurrences} occurrences). Root cause: {pattern.root_cause_id}"
            )

        # New unseen root cause -> alert (simplified: if occurrences == 1 and first_seen == last_seen)
        if pattern.occurrences == 1:
             self._emit_alert(
                rule="new_failure_root_cause",
                severity="info",
                value=1.0,
                message=f"New failure root cause detected: {pattern.root_cause_id} from pattern {pattern.pattern_id}"
            )

    def _emit_alert(self, rule: str, severity: str, value: float, message: str):
        alert = Alert(
            rule=rule,
            severity=severity,
            value=value,
            message=message
        )
        self.alerts_dir.mkdir(parents=True, exist_ok=True)
        date_str = alert.timestamp.strftime("%Y-%m-%d")
        file_path = self.alerts_dir / f"{date_str}.jsonl"
        with open(file_path, "a") as f:
            f.write(alert.model_dump_json() + "\n")

    def _store_signature(self, signature):
        sigs = {}
        if self.signatures_path.exists():
            try:
                with open(self.signatures_path, "r") as f:
                    sigs = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        sigs[signature.signature_id] = signature.model_dump(mode="json")
        with open(self.signatures_path, "w") as f:
            json.dump(sigs, f, indent=2)

    def _store_root_cause(self, rc: RootCause):
        rcs = {}
        if self.root_causes_path.exists():
            try:
                with open(self.root_causes_path, "r") as f:
                    rcs = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        rcs[rc.root_cause_id] = rc.model_dump(mode="json")
        with open(self.root_causes_path, "w") as f:
            json.dump(rcs, f, indent=2)

    def get_patterns(self) -> List[FailurePattern]:
        if not self.patterns_path.exists():
            return []
        try:
            with open(self.patterns_path, "r") as f:
                data = json.load(f)
                return [FailurePattern(**p) for p in data]
        except (json.JSONDecodeError, IOError):
            return []

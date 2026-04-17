import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from .models import Alert, AlertRule, DailyAggregate

class TelemetryAlerts:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.telemetry_dir = workspace_root / "runtime_data" / "telemetry"
        self.alerts_dir = self.telemetry_dir / "alerts"
        self.alerts_dir.mkdir(parents=True, exist_ok=True)

    def get_default_rules(self) -> List[AlertRule]:
        return [
            AlertRule(rule_id="failure_rate_high", condition="failure_rate > 0.1", threshold=0.1, severity="warning"),
            AlertRule(rule_id="failure_rate_critical", condition="failure_rate > 0.2", threshold=0.2, severity="critical"),
            AlertRule(rule_id="drift_rate_high", condition="drift_rate > 0.05", threshold=0.05, severity="warning"),
            AlertRule(rule_id="retry_success_low", condition="retry_success_rate < 0.5", threshold=0.5, severity="warning"),
        ]

    def evaluate_rules(self, agg: DailyAggregate) -> List[Alert]:
        rules = self.get_default_rules()
        alerts = []

        agg_dict = agg.model_dump()

        for rule in rules:
            # Simple condition evaluator for "field > threshold" or "field < threshold"
            field = rule.condition.split()[0]
            op = rule.condition.split()[1]
            val = agg_dict.get(field, 0)

            triggered = False
            if op == ">" and val > rule.threshold:
                triggered = True
            elif op == "<" and val < rule.threshold:
                triggered = True

            if triggered:
                alert = Alert(
                    rule=rule.rule_id,
                    severity=rule.severity,
                    value=float(val),
                    message=f"Rule {rule.rule_id} triggered: {field} is {val} (threshold {rule.threshold})"
                )
                alerts.append(alert)
                self._store_alert(alert)

        return alerts

    def _store_alert(self, alert: Alert):
        file_path = self.alerts_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(file_path, "a") as f:
            f.write(alert.model_dump_json() + "\n")

    def get_recent_alerts(self, days: int = 1) -> List[Alert]:
        alerts = []
        for i in range(days):
            date_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            file_path = self.alerts_dir / f"{date_str}.jsonl"
            if file_path.exists():
                with open(file_path, "r") as f:
                    for line in f:
                        alerts.append(Alert.model_validate_json(line))
        return sorted(alerts, key=lambda x: x.timestamp, reverse=True)

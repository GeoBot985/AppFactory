import os
from pathlib import Path
from datetime import date
from typing import Optional
from .query import TelemetryQuery
from .alerts import TelemetryAlerts
from .aggregator import TelemetryAggregator

class TelemetryDashboard:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.telemetry_dir = workspace_root / "runtime_data" / "telemetry"
        self.query = TelemetryQuery(workspace_root)
        self.alerts = TelemetryAlerts(workspace_root)

    def generate_html(self, output_path: Optional[Path] = None):
        if output_path is None:
            output_path = self.telemetry_dir / "dashboard.html"

        agg = self.query.get_daily_aggregate(date.today())
        recent_alerts = self.alerts.get_recent_alerts(1)

        if not agg:
            # Try to run aggregator if no data for today
            aggregator = TelemetryAggregator(self.workspace_root)
            agg = aggregator.aggregate_day(date.today())

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Demo10 Telemetry Dashboard</title>
    <style>
        body {{ font-family: sans-serif; margin: 20px; background: #f4f4f9; }}
        .card {{ background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1, h2 {{ color: #333; }}
        .metric {{ display: inline-block; width: 200px; margin-right: 20px; margin-bottom: 20px; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #007bff; }}
        .metric-label {{ font-size: 14px; color: #666; }}
        .alert {{ padding: 10px; margin-bottom: 5px; border-radius: 4px; }}
        .critical {{ background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }}
        .warning {{ background: #fff3cd; color: #856404; border: 1px solid #ffeeba; }}
    </style>
</head>
<body>
    <h1>Demo10 System Health Dashboard</h1>
    <p>Generated at: {date.today().isoformat()}</p>

    <div class="card">
        <h2>Execution Metrics</h2>
        <div class="metric"><div class="metric-value">{agg.runs_total}</div><div class="metric-label">Runs Total</div></div>
        <div class="metric"><div class="metric-value">{agg.runs_completed}</div><div class="metric-label">Runs Completed</div></div>
        <div class="metric"><div class="metric-value">{agg.runs_failed}</div><div class="metric-label">Runs Failed</div></div>
        <div class="metric"><div class="metric-value">{agg.failure_rate:.2%}</div><div class="metric-label">Failure Rate</div></div>
    </div>

    <div class="card">
        <h2>Reliability & Recovery</h2>
        <div class="metric"><div class="metric-value">{agg.steps_total}</div><div class="metric-label">Steps Total</div></div>
        <div class="metric"><div class="metric-value">{agg.retries_total}</div><div class="metric-label">Retries Total</div></div>
        <div class="metric"><div class="metric-value">{agg.retry_success_rate:.2%}</div><div class="metric-label">Retry Success Rate</div></div>
        <div class="metric"><div class="metric-value">{agg.reliability_index:.2f}</div><div class="metric-label">Reliability Index</div></div>
    </div>

    <div class="card">
        <h2>Verification & Drift</h2>
        <div class="metric"><div class="metric-value">{agg.verification_runs_total}</div><div class="metric-label">Verification Runs</div></div>
        <div class="metric"><div class="metric-value">{agg.verification_pass}</div><div class="metric-label">Pass</div></div>
        <div class="metric"><div class="metric-value">{agg.verification_fail}</div><div class="metric-label">Fail</div></div>
        <div class="metric"><div class="metric-value">{agg.drift_events_total}</div><div class="metric-label">Drift Events</div></div>
    </div>

    <div class="card">
        <h2>Active Alerts</h2>
        {"".join([f'<div class="alert {a.severity}"><b>{a.severity.upper()}</b>: {a.message}</div>' for a in recent_alerts]) if recent_alerts else "<p>No active alerts.</p>"}
    </div>
</body>
</html>
"""
        with open(output_path, "w") as f:
            f.write(html)
        print(f"Dashboard generated at {output_path}")

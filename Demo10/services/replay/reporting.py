import json
from pathlib import Path
from .models import ReplayResult

class ReplayReporter:
    def __init__(self, workspace_root: Path):
        self.replays_dir = workspace_root / "runtime_data" / "replays"

    def save_report(self, result: ReplayResult):
        replay_dir = self.replays_dir / result.replay_id
        replay_dir.mkdir(parents=True, exist_ok=True)

        report_file = replay_dir / "comparison_report.json"
        with open(report_file, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

        # Basic HTML report
        html_file = replay_dir / "comparison_report.html"
        with open(html_file, "w") as f:
            f.write(self._generate_html(result))

    def _generate_html(self, result: ReplayResult) -> str:
        return f"""
<html>
<head><title>Replay Report - {result.replay_id}</title></head>
<body>
    <h1>Replay Report</h1>
    <p>Replay ID: {result.replay_id}</p>
    <p>Source Run ID: {result.source_run_id}</p>
    <p>Verdict: <b>{result.reproducibility_verdict}</b></p>
    <h2>Comparison</h2>
    <ul>
        <li>Plan Match: {result.comparison.plan_match}</li>
        <li>Step Order Match: {result.comparison.step_order_match}</li>
        <li>Status Match: {result.comparison.status_match}</li>
        <li>Outputs Match: {result.comparison.outputs_match}</li>
    </ul>
</body>
</html>
"""

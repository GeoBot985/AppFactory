from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict
from .models import VerificationReport, RunSummary, CheckStatus, VerificationResult

class ReportingService:
    def generate_json_report(self, run_folder: Path, report: VerificationReport, summary: RunSummary) -> Path:
        data = {
            "spec_id": summary.spec_id,
            "final_status": summary.final_status.value,
            "failure_stage": summary.failure_stage.value if summary.failure_stage else None,
            "tasks": {
                "total": summary.tasks_total,
                "applied": summary.tasks_applied,
                "no_op": summary.tasks_no_op,
                "failed": summary.tasks_failed
            },
            "verification": {
                "summary": report.summary,
                "checks": [
                    {
                        "id": c.check_id,
                        "type": c.type,
                        "severity": c.severity.value,
                        "status": c.status.value,
                        "message": c.message,
                        "evidence": c.evidence
                    } for c in report.checks
                ]
            },
            "regression": summary.regression
        }

        report_path = run_folder / "verification_report.json"
        with open(report_path, "w") as f:
            json.dump(data, f, indent=2)
        return report_path

    def generate_html_report(self, run_folder: Path, report: VerificationReport, summary: RunSummary) -> Path:
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Verification Report - {summary.spec_id}</title>
    <style>
        body {{ font-family: sans-serif; line-height: 1.6; color: #333; max-width: 1000px; margin: 0 auto; padding: 20px; }}
        h1, h2 {{ color: #2c3e50; }}
        .status-badge {{ padding: 5px 10px; border-radius: 4px; font-weight: bold; }}
        .COMPLETED {{ background: #d4edda; color: #155724; }}
        .FAILED {{ background: #f8d7da; color: #721c24; }}
        .PARTIAL_FAILURE {{ background: #fff3cd; color: #856404; }}
        .section {{ margin-bottom: 30px; border: 1px solid #ddd; padding: 15px; border-radius: 4px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background: #f4f4f4; }}
        .PASS {{ color: green; }}
        .FAIL {{ color: red; font-weight: bold; }}
        .WARN {{ color: orange; }}
        .ERROR {{ color: darkred; }}
    </style>
</head>
<body>
    <h1>Verification Report: {summary.spec_id}</h1>

    <div class="section">
        <h2>Overall Status: <span class="status-badge {summary.final_status.value}">{summary.final_status.value}</span></h2>
        <p><strong>Failure Stage:</strong> {summary.failure_stage.value if summary.failure_stage else 'None'}</p>
        <p><strong>Rationale:</strong> {summary.summary}</p>
    </div>

    <div class="section">
        <h2>Execution Summary</h2>
        <ul>
            <li>Total Tasks: {summary.tasks_total}</li>
            <li>Applied: {summary.tasks_applied}</li>
            <li>No-op: {summary.tasks_no_op}</li>
            <li>Failed: {summary.tasks_failed}</li>
        </ul>
    </div>

    <div class="section">
        <h2>Verification Checks</h2>
        <table>
            <thead>
                <tr>
                    <th>Status</th>
                    <th>Check ID</th>
                    <th>Type</th>
                    <th>Severity</th>
                    <th>Message</th>
                </tr>
            </thead>
            <tbody>
"""
        for c in report.checks:
            html += f"""
                <tr>
                    <td class="{c.status.value.upper()}">{c.status.value.upper()}</td>
                    <td>{c.check_id}</td>
                    <td>{c.type}</td>
                    <td>{c.severity.value}</td>
                    <td>{c.message}</td>
                </tr>
"""

        html += """
            </tbody>
        </table>
    </div>

    <div class="section">
        <h2>Regression Status</h2>
        <p>Enabled: """ + str(summary.regression.get("enabled", False)) + """</p>
        <p>Status: """ + str(summary.regression.get("status", "N/A")) + """</p>
    </div>
</body>
</html>
"""
        report_path = run_folder / "verification_report.html"
        with open(report_path, "w") as f:
            f.write(html)
        return report_path

class VerificationHarnessReporter:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.reports_dir = workspace_root / "runtime_data" / "verification"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def save_verification_result(self, result: VerificationResult):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suite_report_dir = self.reports_dir / result.suite_id / timestamp
        suite_report_dir.mkdir(parents=True, exist_ok=True)

        # 1. summary.json
        summary_path = suite_report_dir / "summary.json"
        with open(summary_path, "w") as f:
            json.dump(result.summary, f, indent=2)

        # 2. detailed_report.json
        detailed_path = suite_report_dir / "detailed_report.json"
        with open(detailed_path, "w") as f:
            json.dump(self._to_dict(result), f, indent=2)

        # 3. HTML report
        html_path = suite_report_dir / "report.html"
        self._generate_html(result, html_path)

        print(f"Verification report saved to {suite_report_dir}")

    def _generate_html(self, result: VerificationResult, path: Path):
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Verification Report - {result.suite_id}</title>
    <style>
        body {{ font-family: sans-serif; line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; }}
        h1, h2 {{ color: #2c3e50; }}
        .verdict-badge {{ padding: 10px 20px; border-radius: 4px; font-weight: bold; font-size: 1.2em; display: inline-block; }}
        .pass {{ background: #d4edda; color: #155724; }}
        .pass_with_warnings {{ background: #fff3cd; color: #856404; }}
        .fail {{ background: #f8d7da; color: #721c24; }}
        .section {{ margin-bottom: 30px; border: 1px solid #ddd; padding: 20px; border-radius: 4px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background: #f4f4f4; }}
        tr:nth-child(even) {{ background: #f9f9f9; }}
        .status-pass {{ color: green; font-weight: bold; }}
        .status-warn {{ color: orange; font-weight: bold; }}
        .status-fail {{ color: red; font-weight: bold; }}
        .drift-tag {{ background: #eee; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; margin-right: 5px; }}
    </style>
</head>
<body>
    <h1>Verification Report: {result.suite_id}</h1>

    <div class="section">
        <h2>Overall Verdict: <span class="verdict-badge {result.overall_verdict}">{result.overall_verdict.upper()}</span></h2>
        <p><strong>Timestamp:</strong> {result.summary['timestamp']}</p>
        <p><strong>Summary:</strong> {result.summary['pass']} Pass, {result.summary['warn']} Warning, {result.summary['fail']} Fail / {result.summary['total_runs']} Total</p>
    </div>

    <div class="section">
        <h2>Run Breakdown</h2>
        <table>
            <thead>
                <tr>
                    <th>Classification</th>
                    <th>Golden Run ID</th>
                    <th>Replay Verdict</th>
                    <th>Drift Categories</th>
                </tr>
            </thead>
            <tbody>
"""
        for r in result.run_results:
            drift_tags = "".join([f'<span class="drift-tag">{d}</span>' for d in r.drift_categories])
            html += f"""
                <tr>
                    <td><span class="status-{r.classification}">{r.classification.upper()}</span></td>
                    <td>{r.golden_run_id}</td>
                    <td>{r.verdict}</td>
                    <td>{drift_tags}</td>
                </tr>
"""

        html += """
            </tbody>
        </table>
    </div>
</body>
</html>
"""
        with open(path, "w") as f:
            f.write(html)

    def _to_dict(self, obj: Any) -> Dict[str, Any]:
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "__dict__"):
            return {k: self._to_dict(v) for k, v in obj.__dict__.items()}
        if isinstance(obj, list):
            return [self._to_dict(i) for i in obj]
        if isinstance(obj, dict):
            return {k: self._to_dict(v) for k, v in obj.items()}
        if hasattr(obj, "value"): # for Enums
            return obj.value
        return str(obj) if not isinstance(obj, (int, float, bool, type(None))) else obj

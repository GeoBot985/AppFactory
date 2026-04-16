from __future__ import annotations
import json
from pathlib import Path
from .models import VerificationReport, RunSummary, CheckStatus

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

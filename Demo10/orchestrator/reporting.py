from pathlib import Path
import json

def generate_html_report(bundle_dir: Path, result: 'SingleCommandResult'):
    report_path = bundle_dir / "report.html"

    # Very simple HTML report for the demo
    html = f"""
<html>
<head>
    <title>Single Command Report - {result.request_id}</title>
    <style>
        body {{ font-family: sans-serif; margin: 20px; }}
        .header {{ background: #f0f0f0; padding: 10px; border-radius: 5px; }}
        .status {{ font-weight: bold; font-size: 1.2em; }}
        .completed {{ color: green; }}
        .failed {{ color: red; }}
        .blocked {{ color: orange; }}
        .rejected {{ color: brown; }}
        .section {{ margin-top: 20px; border: 1px solid #ddd; padding: 10px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Single Command Result</h1>
        <p>Request ID: {result.request_id}</p>
        <p class="status {result.final_status}">Final Status: {result.final_status.upper()}</p>
    </div>

    <div class="section">
        <h2>Summary</h2>
        <ul>
            <li>Compile Status: {result.compile_status}</li>
            <li>Repair Iterations: {result.repair_iterations}</li>
            <li>Plan ID: {result.plan_id}</li>
            <li>Run ID: {result.run_id}</li>
            <li>Verification Verdict: {result.summary.get('verification_verdict', 'N/A')}</li>
            <li>Promotion Decision: {result.summary.get('promotion_decision', 'N/A')}</li>
        </ul>
    </div>

    <div class="section">
        <h2>Input & Compilation</h2>
        <p><strong>Input:</strong> {getattr(result, 'input_text', 'See input.txt')}</p>
        <p><strong>Compile status:</strong> {result.compile_status}</p>
    </div>

    <div class="section">
        <h2>Plan & Routing</h2>
        <p><strong>Plan ID:</strong> {result.plan_id}</p>
        <p><strong>Macro Used:</strong> {result.summary.get('macro_used', False)}</p>
    </div>

    <div class="section">
        <h2>Execution & Verification</h2>
        <ul>
            <li>Steps Executed: {result.summary.get('steps_executed', 0)}</li>
            <li>Retries: {result.summary.get('retries', 0)}</li>
            <li>Rollback Used: {result.summary.get('rollback_used', False)}</li>
            <li>Consistency Outcome: {getattr(result, 'consistency_outcome', 'N/A')}</li>
        </ul>
        <p><strong>Verification Verdict:</strong> {result.summary.get('verification_verdict', 'N/A')}</p>
    </div>

    <div class="section">
        <h2>Diagnostics & Suggestions</h2>
        <p>Refer to <code>diagnostics.json</code> for details.</p>
    </div>
</body>
</html>
"""
    with open(report_path, "w") as f:
        f.write(html)

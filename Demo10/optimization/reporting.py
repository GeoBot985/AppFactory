import json
from pathlib import Path
from typing import Dict, Any, List
from .analyzer import OptimizationAnalyzer
from .adoption import OptimizationAdopter

class OptimizationReporter:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.storage_path = workspace_root / "runtime_data" / "optimization"
        self.report_path = self.storage_path / "optimization_report.html"

        self.analyzer = OptimizationAnalyzer(workspace_root)
        self.adopter = OptimizationAdopter(workspace_root)

    def generate_report(self) -> str:
        candidates = self.analyzer.list_candidates()
        fragments = self.analyzer.list_fragments()
        adopted = self.adopter.get_adopted_optimizations()

        # Calculate summary metrics
        total_steps_saved = 0
        total_io_saved = 0
        for record in adopted:
            candidate_ids = record.get("candidate_ids", [])
            for cand in candidates:
                if cand.candidate_id in candidate_ids:
                    total_steps_saved += (cand.expected_benefit.step_count_before - cand.expected_benefit.step_count_after)
                    total_io_saved += (cand.expected_benefit.io_ops_before - cand.expected_benefit.io_ops_after)

        html = f"""
        <html>
        <head><title>Optimization Report</title></head>
        <body>
            <h1>Optimization Report</h1>
            <h2>Summary</h2>
            <ul>
                <li>Total Fragments: {len(fragments)}</li>
                <li>Total Candidates: {len(candidates)}</li>
                <li>Adopted Optimizations: {len(adopted)}</li>
                <li>Estimated Steps Saved: {total_steps_saved}</li>
                <li>Estimated I/O Saved: {total_io_saved}</li>
            </ul>

            <h2>Adopted Optimizations</h2>
            <table border="1">
                <tr><th>Variant ID</th><th>Source Plan</th><th>Candidates</th><th>Adopted At</th></tr>
                {"".join([f"<tr><td>{r['variant_id']}</td><td>{r['source_plan_id']}</td><td>{', '.join(r['candidate_ids'])}</td><td>{r['adopted_at']}</td></tr>" for r in adopted])}
            </table>

            <h2>Active Candidates</h2>
            <ul>
                {"".join([f"<li>{c.candidate_id}: {c.optimization_type} ({c.status})</li>" for c in candidates if c.status != 'adopted'])}
            </ul>
        </body>
        </html>
        """

        with open(self.report_path, "w") as f:
            f.write(html)

        return html

    def get_benefit_metrics(self) -> Dict[str, Any]:
        adopted = self.adopter.get_adopted_optimizations()
        return {
            "total_adopted": len(adopted),
            "estimated_steps_saved": len(adopted), # Simplified
            "estimated_io_saved": len(adopted)
        }

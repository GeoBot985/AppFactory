from __future__ import annotations

from conftest import load_diagram, load_metrics


REQUIRED_NOISE_FIELDS = [
    "noise_artifacts_rejected",
    "noise_internal_rejected",
    "noise_node_candidates_rejected",
    "noise_segments_filtered_pre_intersection",
    "noise_intersections_rejected",
    "noise_spurs_pruned",
    "noise_final_components_pruned",
]


def test_noise_metrics_export_contract() -> None:
    for diagram_id in ("Diagram1", "Diagram2"):
        data = load_diagram(diagram_id)
        metrics = load_metrics(diagram_id)
        noise_metrics = data.get("metadata", {}).get("noise_metrics")

        assert isinstance(noise_metrics, dict), f"{diagram_id} metadata.noise_metrics missing or not a dict"
        for field in REQUIRED_NOISE_FIELDS:
            assert field in noise_metrics, f"{diagram_id} metadata.noise_metrics missing {field}"
            assert field in metrics, f"{diagram_id} metrics.json missing {field}"
            assert isinstance(noise_metrics[field], int), f"{diagram_id} {field}={noise_metrics[field]!r}, expected int"
            assert isinstance(metrics[field], int), f"{diagram_id} metrics {field}={metrics[field]!r}, expected int"
            assert noise_metrics[field] == metrics[field], (
                f"{diagram_id} noise metric drift for {field}: metadata={noise_metrics[field]} metrics={metrics[field]}"
            )

        summary = data.get("separation_summary", {})
        expected_rejected = max(
            int(summary.get("intersections_detected_raw", 0)) - int(summary.get("intersections_accepted_initial", 0)),
            0,
        )
        assert noise_metrics["noise_intersections_rejected"] == expected_rejected, (
            f"{diagram_id} noise_intersections_rejected={noise_metrics['noise_intersections_rejected']}, "
            f"expected {expected_rejected}"
        )

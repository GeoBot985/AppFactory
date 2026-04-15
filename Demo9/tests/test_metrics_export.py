from __future__ import annotations

from conftest import load_diagram, load_metrics


def test_metrics_json_matches_diagram_json() -> None:
    for diagram_id in ("Diagram1", "Diagram2"):
        data = load_diagram(diagram_id)
        metrics = load_metrics(diagram_id)
        summary = data.get("separation_summary", {})
        verification = data.get("verification", {})

        assert metrics.get("diagram_id") == diagram_id, (
            f"{diagram_id} metrics diagram_id={metrics.get('diagram_id')}, expected {diagram_id}"
        )
        expected_values = {
            "route_count": summary.get("route_count"),
            "graph_vertices": summary.get("graph_vertices"),
            "graph_edges": summary.get("graph_edges"),
            "final_graph_vertices": summary.get("final_graph_vertices"),
            "final_graph_edges": summary.get("final_graph_edges"),
            "final_graph_junction_vertices": summary.get("final_graph_junction_vertices"),
            "final_graph_bend_vertices": summary.get("final_graph_bend_vertices"),
            "final_graph_endpoint_vertices": summary.get("final_graph_endpoint_vertices"),
            "verification_status": verification.get("status"),
            "edge_overlap_score": verification.get("edge_overlap_score"),
            "pixel_difference_score": verification.get("pixel_difference_score"),
            "intersections_detected_raw": summary.get("intersections_detected_raw"),
            "intersections_accepted_initial": summary.get("intersections_accepted_initial"),
            "intersections_accepted": summary.get("intersections_accepted"),
            "segments_split_initial": summary.get("segments_split_initial"),
            "segments_split": summary.get("segments_split"),
            "split_edges_created_initial": summary.get("split_edges_created_initial"),
            "split_edges_created": summary.get("split_edges_created"),
            "junction_vertices_created": summary.get("junction_vertices_created"),
            "degree2_endpoints_reclassified": summary.get("degree2_endpoints_reclassified"),
            "gate_stubs_absorbed": summary.get("gate_stubs_absorbed"),
            "micro_bends_removed": summary.get("micro_bends_removed"),
            "corridor_contacts_snapped": summary.get("corridor_contacts_snapped"),
            "noise_artifacts_rejected": data.get("metadata", {}).get("noise_metrics", {}).get("noise_artifacts_rejected"),
            "noise_internal_rejected": data.get("metadata", {}).get("noise_metrics", {}).get("noise_internal_rejected"),
            "noise_node_candidates_rejected": data.get("metadata", {}).get("noise_metrics", {}).get("noise_node_candidates_rejected"),
            "noise_segments_filtered_pre_intersection": data.get("metadata", {}).get("noise_metrics", {}).get("noise_segments_filtered_pre_intersection"),
            "noise_intersections_rejected": data.get("metadata", {}).get("noise_metrics", {}).get("noise_intersections_rejected"),
            "noise_spurs_pruned": data.get("metadata", {}).get("noise_metrics", {}).get("noise_spurs_pruned"),
            "noise_final_components_pruned": data.get("metadata", {}).get("noise_metrics", {}).get("noise_final_components_pruned"),
        }
        for key, expected in expected_values.items():
            assert key in metrics, f"{diagram_id} metrics.json missing key {key}"
            assert metrics[key] == expected, (
                f"{diagram_id} metrics.json {key}={metrics[key]!r}, expected {expected!r} from diagram.json"
            )

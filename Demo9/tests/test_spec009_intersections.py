from __future__ import annotations

from conftest import load_diagram


def test_diagram1_spec009_intersection_metrics() -> None:
    data = load_diagram("Diagram1")
    summary = data.get("separation_summary", {})
    required_fields = [
        "intersections_detected_raw",
        "intersections_accepted",
        "junction_vertices_created",
        "segments_split",
        "split_edges_created",
    ]
    missing = [field for field in required_fields if field not in summary]
    assert not missing, f"Diagram1 missing Spec 009 fields: {missing}"

    assert summary["intersections_accepted"] > 0, (
        f"Diagram1 intersections_accepted={summary['intersections_accepted']}, expected > 0"
    )
    assert summary["junction_vertices_created"] > 0, (
        f"Diagram1 junction_vertices_created={summary['junction_vertices_created']}, expected > 0"
    )
    assert summary["segments_split"] > 0, f"Diagram1 segments_split={summary['segments_split']}, expected > 0"
    assert summary["split_edges_created"] > 0, (
        f"Diagram1 split_edges_created={summary['split_edges_created']}, expected > 0"
    )


def test_diagram2_spec009_intersection_metrics() -> None:
    data = load_diagram("Diagram2")
    summary = data.get("separation_summary", {})
    required_fields = [
        "intersections_detected_raw",
        "intersections_accepted",
        "junction_vertices_created",
        "segments_split",
        "split_edges_created",
    ]
    missing = [field for field in required_fields if field not in summary]
    assert not missing, f"Diagram2 missing Spec 009 fields: {missing}"
    for field in required_fields:
        value = summary[field]
        assert isinstance(value, int), f"Diagram2 {field}={value!r}, expected int"
        assert value >= 0, f"Diagram2 {field}={value}, expected >= 0"
    assert summary["intersections_accepted"] > 0, (
        f"Diagram2 intersections_accepted={summary['intersections_accepted']}, expected > 0"
    )
    assert summary["segments_split"] > 0, f"Diagram2 segments_split={summary['segments_split']}, expected > 0"
    assert summary["split_edges_created"] > 0, (
        f"Diagram2 split_edges_created={summary['split_edges_created']}, expected > 0"
    )

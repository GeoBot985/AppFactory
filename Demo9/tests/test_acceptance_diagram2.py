from __future__ import annotations

from conftest import load_diagram


def test_diagram2_acceptance_metrics() -> None:
    data = load_diagram("Diagram2")
    summary = data.get("separation_summary", {})
    graph = data.get("graph", {})
    nodes = data.get("nodes", [])
    verification = data.get("verification", {})

    route_count = summary.get("route_count")
    verification_status = verification.get("status")

    assert isinstance(graph, dict) and graph, "Diagram2 graph is missing or empty"
    assert len(nodes) >= 6, f"Diagram2 node_count={len(nodes)}, expected >= 6"
    assert route_count is not None, "Diagram2 missing separation_summary.route_count"
    assert route_count >= 3, f"Diagram2 route_count={route_count}, expected >= 3"
    assert verification_status != "fail", f"Diagram2 verification_status={verification_status}, expected != fail"

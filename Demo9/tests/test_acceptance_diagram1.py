from __future__ import annotations

from conftest import load_diagram, route_pairs


def test_diagram1_acceptance_metrics() -> None:
    data = load_diagram("Diagram1")
    summary = data.get("separation_summary", {})
    graph = data.get("graph", {})
    routes = data.get("routes", [])
    nodes = data.get("nodes", [])
    verification = data.get("verification", {})

    route_count = summary.get("route_count")
    graph_vertices = summary.get("graph_vertices")
    degree2_endpoints_reclassified = summary.get("degree2_endpoints_reclassified")
    gate_stubs_absorbed = summary.get("gate_stubs_absorbed")
    verification_status = verification.get("status")

    assert isinstance(graph, dict) and graph, "Diagram1 graph is missing or empty"
    assert routes, "Diagram1 routes list is empty"
    assert len(nodes) >= 6, f"Diagram1 node_count={len(nodes)}, expected >= 6"
    assert route_count is not None, "Diagram1 missing separation_summary.route_count"
    assert route_count >= 3, f"Diagram1 route_count={route_count}, expected >= 3"
    assert graph_vertices is not None, "Diagram1 missing separation_summary.graph_vertices"
    assert graph_vertices < 55, f"Diagram1 graph_vertices={graph_vertices}, expected < 55"
    assert degree2_endpoints_reclassified is not None, "Diagram1 missing separation_summary.degree2_endpoints_reclassified"
    assert degree2_endpoints_reclassified > 0, (
        f"Diagram1 degree2_endpoints_reclassified={degree2_endpoints_reclassified}, expected > 0"
    )
    assert gate_stubs_absorbed is not None, "Diagram1 missing separation_summary.gate_stubs_absorbed"
    assert gate_stubs_absorbed > 0, f"Diagram1 gate_stubs_absorbed={gate_stubs_absorbed}, expected > 0"
    assert verification_status != "fail", f"Diagram1 verification_status={verification_status}, expected != fail"


def test_diagram1_required_route_pairs() -> None:
    data = load_diagram("Diagram1")
    pairs = route_pairs(data)

    required_pair = tuple(sorted(("node_002", "node_007")))
    assert required_pair in pairs, f"Diagram1 missing required route pair {required_pair}; found={sorted(pairs)}"

    # TODO: Add stable semantic pair assertions for the expected restored Diagram1 routes once node mapping is deterministic.

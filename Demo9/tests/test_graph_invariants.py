from __future__ import annotations

from conftest import load_diagram


def test_graph_invariants() -> None:
    for diagram_id in ("Diagram1", "Diagram2"):
        data = load_diagram(diagram_id)
        graph = data.get("graph", {})
        vertices = graph.get("vertices", [])
        edges = graph.get("edges", [])
        routes = data.get("routes", [])

        vertex_ids = [vertex.get("id") for vertex in vertices]
        edge_ids = [edge.get("id") for edge in edges]
        vertex_id_set = set(vertex_ids)

        assert len(vertex_ids) == len(vertex_id_set), f"{diagram_id} duplicate vertex IDs detected"
        assert len(edge_ids) == len(set(edge_ids)), f"{diagram_id} duplicate edge IDs detected"

        for edge in edges:
            assert edge.get("v_start") in vertex_id_set, (
                f"{diagram_id} edge {edge.get('id')} references missing start vertex {edge.get('v_start')}"
            )
            assert edge.get("v_end") in vertex_id_set, (
                f"{diagram_id} edge {edge.get('id')} references missing end vertex {edge.get('v_end')}"
            )
            length = edge.get("length")
            assert length is not None and length > 0, f"{diagram_id} edge {edge.get('id')} length={length}, expected > 0"
            debug = edge.get("debug", {})
            assert "source_segment_id" in debug, f"{diagram_id} edge {edge.get('id')} missing debug.source_segment_id"
            assert "source_segment_stage" in debug, f"{diagram_id} edge {edge.get('id')} missing debug.source_segment_stage"
            assert debug.get("source_segment_stage") == "collapsed_segments", (
                f"{diagram_id} edge {edge.get('id')} source_segment_stage={debug.get('source_segment_stage')}, expected collapsed_segments"
            )
            assert "split_from_intersection" in debug, (
                f"{diagram_id} edge {edge.get('id')} missing debug.split_from_intersection"
            )

        for route in routes:
            vertex_path = route.get("vertex_path", [])
            points = route.get("points", [])
            for field in ("id", "src_node_id", "src_side", "dst_node_id", "dst_side", "vertex_path", "points", "confidence", "debug"):
                assert field in route, f"{diagram_id} route missing field {field}"
            route_debug = route.get("debug", {})
            for field in ("simplified_edge_count", "fallback_used", "attachment_pair", "stub_absorbed"):
                assert field in route_debug, f"{diagram_id} route {route.get('id')} missing debug.{field}"
            for vertex_id in vertex_path:
                assert vertex_id in vertex_id_set, (
                    f"{diagram_id} route {route.get('id')} references missing vertex {vertex_id}"
                )
            assert len(points) >= 2, f"{diagram_id} route {route.get('id')} points_len={len(points)}, expected >= 2"

        bad = [vertex for vertex in vertices if vertex.get("kind") == "endpoint" and vertex.get("degree") == 2]
        assert not bad, f"{diagram_id} has endpoint vertices with degree 2: {[vertex.get('id') for vertex in bad]}"

        summary = data.get("separation_summary", {})
        final_vertex_count = len(vertices)
        final_junctions = sum(1 for vertex in vertices if vertex.get("degree", 0) >= 3)
        final_bends = sum(1 for vertex in vertices if vertex.get("degree") == 2)
        final_endpoints = sum(1 for vertex in vertices if vertex.get("degree") == 1)

        assert summary.get("final_graph_vertices") == final_vertex_count, (
            f"{diagram_id} final_graph_vertices={summary.get('final_graph_vertices')}, expected {final_vertex_count}"
        )
        assert summary.get("final_graph_edges") == len(edges), (
            f"{diagram_id} final_graph_edges={summary.get('final_graph_edges')}, expected {len(edges)}"
        )
        assert summary.get("final_graph_junction_vertices") == final_junctions, (
            f"{diagram_id} final_graph_junction_vertices={summary.get('final_graph_junction_vertices')}, expected {final_junctions}"
        )
        assert summary.get("final_graph_bend_vertices") == final_bends, (
            f"{diagram_id} final_graph_bend_vertices={summary.get('final_graph_bend_vertices')}, expected {final_bends}"
        )
        assert summary.get("final_graph_endpoint_vertices") == final_endpoints, (
            f"{diagram_id} final_graph_endpoint_vertices={summary.get('final_graph_endpoint_vertices')}, expected {final_endpoints}"
        )
        assert summary.get("graph_vertices") == summary.get("final_graph_vertices"), (
            f"{diagram_id} graph_vertices alias drift: {summary.get('graph_vertices')} vs {summary.get('final_graph_vertices')}"
        )
        assert summary.get("graph_edges") == summary.get("final_graph_edges"), (
            f"{diagram_id} graph_edges alias drift: {summary.get('graph_edges')} vs {summary.get('final_graph_edges')}"
        )
        assert summary.get("junction_vertices_created") == summary.get("final_graph_junction_vertices"), (
            f"{diagram_id} junction_vertices_created alias drift: {summary.get('junction_vertices_created')} vs {summary.get('final_graph_junction_vertices')}"
        )

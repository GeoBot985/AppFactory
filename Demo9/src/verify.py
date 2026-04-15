from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

from .graph import summarize_final_graph
from .models import Verification


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def verify_render(
    normalized_binary: np.ndarray,
    rendered_image: np.ndarray,
    edge_overlap_pass: float,
    edge_overlap_warn: float,
    pixel_diff_pass: float,
    pixel_diff_warn: float,
    canny_low: int,
    canny_high: int,
    aperture_size: int,
) -> tuple[Verification, np.ndarray]:
    rendered_gray = cv2.cvtColor(rendered_image, cv2.COLOR_BGR2GRAY)
    _, rendered_binary = cv2.threshold(rendered_gray, 200, 255, cv2.THRESH_BINARY_INV)

    source_edges = cv2.Canny(normalized_binary, canny_low, canny_high, apertureSize=aperture_size, L2gradient=True)
    rendered_edges = cv2.Canny(rendered_binary, canny_low, canny_high, apertureSize=aperture_size, L2gradient=True)

    kernel = np.ones((3, 3), dtype=np.uint8)
    dilated_source_edges = cv2.dilate(source_edges, kernel, iterations=1)
    dilated_rendered_edges = cv2.dilate(rendered_edges, kernel, iterations=1)

    source_hits = cv2.bitwise_and(dilated_source_edges, rendered_edges)
    rendered_hits = cv2.bitwise_and(dilated_rendered_edges, source_edges)
    source_edge_count = int(cv2.countNonZero(source_edges))
    rendered_edge_count = int(cv2.countNonZero(rendered_edges))
    source_coverage = _safe_ratio(int(cv2.countNonZero(source_hits)), source_edge_count)
    rendered_coverage = _safe_ratio(int(cv2.countNonZero(rendered_hits)), rendered_edge_count)
    edge_overlap_score = (source_coverage + rendered_coverage) / 2.0
    overlap_mask = cv2.bitwise_or(source_hits, rendered_hits)

    diff_mask = cv2.absdiff(normalized_binary, rendered_binary)
    pixel_difference_score = _safe_ratio(
        int(cv2.countNonZero(diff_mask)),
        diff_mask.shape[0] * diff_mask.shape[1],
    )

    notes: list[str] = []
    if edge_overlap_score >= edge_overlap_pass and pixel_difference_score <= pixel_diff_pass:
        status = "pass"
        notes.append("Rendered output closely matches the normalized source.")
    elif edge_overlap_score >= edge_overlap_warn and pixel_difference_score <= pixel_diff_warn:
        status = "warn"
        notes.append("Rendered output is usable but shows moderate mismatch.")
    else:
        status = "fail"
        notes.append("Rendered output diverges significantly from the normalized source.")

    diff_bgr = cv2.cvtColor(diff_mask, cv2.COLOR_GRAY2BGR)
    diff_bgr[np.where(overlap_mask > 0)] = (0, 255, 0)

    verification = Verification(
        edge_overlap_score=round(edge_overlap_score, 4),
        pixel_difference_score=round(pixel_difference_score, 4),
        status=status,
        notes=notes,
    )
    return verification, diff_bgr


def load_diagram_output(output_dir: Path, diagram_id: str) -> dict:
    path = output_dir / diagram_id / "diagram.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing diagram output: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def _required_metric(summary: dict, field: str, diagram_id: str, failures: list[str]) -> int | float | str | None:
    if field not in summary:
        failures.append(f"missing separation_summary.{field}")
        return None
    return summary[field]


def validate_diagram1(data: dict) -> list[str]:
    failures: list[str] = []
    summary = data.get("separation_summary")
    graph = data.get("graph")
    routes = data.get("routes")
    nodes = data.get("nodes")
    verification = data.get("verification")

    if not isinstance(summary, dict):
        return ["missing separation_summary"]
    if not isinstance(graph, dict) or not graph:
        failures.append("graph missing or empty")
    if not isinstance(routes, list) or not routes:
        failures.append("routes missing or empty")
    if not isinstance(nodes, list):
        failures.append("nodes missing")
        nodes = []
    if not isinstance(verification, dict):
        failures.append("verification missing")
        verification = {}

    route_count = _required_metric(summary, "route_count", "Diagram1", failures)
    graph_vertices = _required_metric(summary, "graph_vertices", "Diagram1", failures)
    degree2_endpoints_reclassified = _required_metric(summary, "degree2_endpoints_reclassified", "Diagram1", failures)
    gate_stubs_absorbed = _required_metric(summary, "gate_stubs_absorbed", "Diagram1", failures)
    intersections_accepted = _required_metric(summary, "intersections_accepted", "Diagram1", failures)
    verification_status = verification.get("status")

    if route_count is not None and route_count < 3:
        failures.append(f"route_count={route_count}, expected >= 3")
    if graph_vertices is not None and graph_vertices >= 55:
        failures.append(f"graph_vertices={graph_vertices}, expected < 55")
    if degree2_endpoints_reclassified is not None and degree2_endpoints_reclassified <= 0:
        failures.append(
            f"degree2_endpoints_reclassified={degree2_endpoints_reclassified}, expected > 0"
        )
    if gate_stubs_absorbed is not None and gate_stubs_absorbed <= 0:
        failures.append(f"gate_stubs_absorbed={gate_stubs_absorbed}, expected > 0")
    if intersections_accepted is not None and intersections_accepted <= 0:
        failures.append(f"intersections_accepted={intersections_accepted}, expected > 0")
    if len(nodes) < 6:
        failures.append(f"node_count={len(nodes)}, expected >= 6")
    if verification_status == "fail":
        failures.append("verification_status=fail")

    return failures


def validate_diagram2(data: dict) -> list[str]:
    failures: list[str] = []
    summary = data.get("separation_summary")
    graph = data.get("graph")
    nodes = data.get("nodes")
    verification = data.get("verification")

    if not isinstance(summary, dict):
        return ["missing separation_summary"]
    if not isinstance(graph, dict) or not graph:
        failures.append("graph missing or empty")
    if not isinstance(nodes, list):
        failures.append("nodes missing")
        nodes = []
    if not isinstance(verification, dict):
        failures.append("verification missing")
        verification = {}

    route_count = _required_metric(summary, "route_count", "Diagram2", failures)
    verification_status = verification.get("status")

    if route_count is not None and route_count < 3:
        failures.append(f"route_count={route_count}, expected >= 3")
    if len(nodes) < 6:
        failures.append(f"node_count={len(nodes)}, expected >= 6")
    if verification_status == "fail":
        failures.append("verification_status=fail")

    return failures


def _run_pipeline(project_root: Path) -> None:
    subprocess.run([sys.executable, "Demo9/app.py"], cwd=project_root, check=True)


def main() -> int:
    demo9_root = Path(__file__).resolve().parents[1]
    project_root = demo9_root.parent
    output_dir = demo9_root / "outputs"
    required_outputs = [
        output_dir / "Diagram1" / "diagram.json",
        output_dir / "Diagram2" / "diagram.json",
    ]
    if not all(path.exists() for path in required_outputs):
        _run_pipeline(project_root)

    failures_by_diagram: dict[str, list[str]] = {}
    loader_errors: list[str] = []
    for diagram_id, validator in (("Diagram1", validate_diagram1), ("Diagram2", validate_diagram2)):
        try:
            data = load_diagram_output(output_dir, diagram_id)
        except (FileNotFoundError, ValueError) as exc:
            failures_by_diagram[diagram_id] = [str(exc)]
            loader_errors.append(diagram_id)
            continue
        failures_by_diagram[diagram_id] = validator(data)

    exit_code = 0
    for diagram_id in ("Diagram1", "Diagram2"):
        failures = failures_by_diagram.get(diagram_id, [f"{diagram_id} was not evaluated"])
        if failures:
            exit_code = 1
            print(f"[FAIL] {diagram_id}")
            for failure in failures:
                print(f"  - {failure}")
        else:
            data = load_diagram_output(output_dir, diagram_id)
            summary = data.get("separation_summary", {})
            verification = data.get("verification", {})
            final_graph = summarize_final_graph(data.get("graph", {}).get("vertices", []), data.get("graph", {}).get("edges", []))
            noise_metrics = data.get("metadata", {}).get("noise_metrics", {})
            print(
                f"[PASS] {diagram_id} "
                f"route_count={summary.get('route_count')} "
                f"graph_vertices={summary.get('graph_vertices')} "
                f"junctions={final_graph.get('final_graph_junction_vertices')} "
                f"noise_internal={noise_metrics.get('noise_internal_rejected')} "
                f"spurs={noise_metrics.get('noise_spurs_pruned')} "
                f"bends={final_graph.get('final_graph_bend_vertices')} "
                f"endpoints={final_graph.get('final_graph_endpoint_vertices')} "
                f"verification={verification.get('status')}"
            )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

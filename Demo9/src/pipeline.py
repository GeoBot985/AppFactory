from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from .connectors import (
    build_protected_node_mask,
    connector_space_from_masks,
    extract_connector_fragments,
    merge_connector_fragments,
    snap_connector_endpoints_to_nodes,
)
from .contours import extract_primitives
from .debug_outputs import write_image, write_json, write_text
from .edges import detect_edges
from .graph import attach_gates_to_graph, build_graph, build_ortho_segments, orthogonalize_paths, route_recovered_paths_via_graph, run_simplification_self_test
from .graph import (
    collapse_parallel_corridors,
    filter_graph_to_gate_reachable,
    filter_graph_to_routes,
    filter_dominant_segments,
    graph_sanity,
    iterative_collinear_merge,
    normalize_ortho_segments,
    prune_spurs,
    reduce_degree2_vertices,
    summarize_final_graph,
)
from .geometry import bbox_contains, bbox_iou, build_connector, build_node_from_element
from .image_io import load_image
from .json_export import export_document
from .models import Connector, DiagramDocument, Element, InterpretedGeometry, Node, ProcessingSummary, RawGeometry, Verification
from .preprocess import normalize_image
from .render import (
    overlay_gates,
    overlay_graph,
    overlay_interpretation,
    overlay_nodes,
    overlay_segments,
    overlay_vertices,
    render_structure,
)
from .separation import SeparationCandidate, separate_geometry
from .verify import verify_render


@dataclass(frozen=True)
class PipelineParameters:
    blur_kernel_size: int = 5
    clahe_clip_limit: float = 2.0
    clahe_grid_size: int = 8
    adaptive_block_size: int = 31
    adaptive_c: int = 7
    canny_low: int = 50
    canny_high: int = 150
    canny_aperture_size: int = 3
    min_contour_area: int = 150
    contour_epsilon_ratio: float = 0.02
    shape_close_kernel_size: int = 7
    shape_dilate_kernel_size: int = 3
    min_shape_area: int = 250
    max_shape_area_ratio: float = 0.28
    artifact_border_margin: int = 6
    artifact_border_touch_reject_count: int = 2
    artifact_extreme_span_ratio: float = 0.88
    artifact_frame_fill_ratio_threshold: float = 0.35
    internal_containment_margin: int = 5
    internal_small_box_area_limit: int = 1400
    internal_text_like_max_height: int = 18
    internal_text_like_aspect_ratio: float = 3.0
    internal_child_area_ratio_threshold: float = 0.16
    internal_child_bbox_area_ratio_threshold: float = 0.18
    node_outward_padding: int = 6
    node_inward_padding: int = 2
    node_gate_padding: int = 3
    node_gate_min_span: int = 6
    node_gate_max_span: int = 14
    node_label_height_ratio: float = 0.35
    node_overlap_reject_iou: float = 0.32
    node_contains_multiple_reject: int = 2
    connector_hough_threshold: int = 12
    connector_min_line_length: int = 12
    connector_max_line_gap: int = 18
    connector_orientation_tolerance: float = 10.0
    connector_merge_gap_threshold: int = 18
    connector_merge_angle_tolerance: float = 10.0
    connector_min_merged_path_length: int = 18
    connector_snap_distance_tolerance: int = 18
    connector_directional_axis_ratio: float = 1.4
    graph_orth_axis_tolerance: int = 3
    graph_spur_min_length: int = 12
    graph_intersection_continuity_radius: int = 2
    graph_endpoint_intersection_tolerance: int = 8
    graph_gate_attach_tolerance: int = 20
    simplify_axis_snap_tolerance: int = 3
    simplify_merge_gap_tolerance: int = 18
    simplify_parallel_offset_tolerance: int = 3
    corridor_overlap_ratio_min: float = 0.2
    corridor_parallel_distance_max: int = 4
    corridor_min_group_size: int = 2
    spur_prune_length: int = 12
    graph_component_gate_distance_max: int = 25
    graph_micro_bend_threshold: int = 10
    graph_vertices_warn: int = 80
    graph_vertices_fail: int = 120
    graph_edges_warn: int = 100
    graph_edges_fail: int = 160
    expected_min_nodes: int = 6
    edge_overlap_pass: float = 0.5
    edge_overlap_warn: float = 0.25
    pixel_diff_pass: float = 0.08
    pixel_diff_warn: float = 0.16


def discover_input_images(base_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    search_dirs = [base_dir, base_dir / "inputs"]

    seen: set[Path] = set()
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for pattern in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
            for path in sorted(search_dir.glob(pattern)):
                resolved = path.resolve()
                if resolved not in seen and path.is_file():
                    candidates.append(path)
                    seen.add(resolved)
    return candidates


def _draw_lines(image: np.ndarray, line_paths: list[list[tuple[int, int]]], color: tuple[int, int, int] = (0, 128, 255)) -> np.ndarray:
    canvas = image.copy()
    for path in line_paths:
        if len(path) < 2:
            continue
        points = np.array(path, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(canvas, [points], False, color, 2)
    return canvas


def _draw_points(image: np.ndarray, points: list[tuple[int, int]], color: tuple[int, int, int]) -> np.ndarray:
    canvas = image.copy()
    for point in points:
        cv2.circle(canvas, point, 3, color, thickness=cv2.FILLED)
    return canvas


def _draw_candidate_overlay(image: np.ndarray, candidates: list[SeparationCandidate], color: tuple[int, int, int]) -> np.ndarray:
    canvas = image.copy()
    for candidate in candidates:
        cv2.drawContours(canvas, [candidate.contour], -1, color, 2)
    return canvas


def _draw_corridor_group_debug(
    image: np.ndarray,
    segments_by_id: dict[str, object],
    group_debug: list[dict[str, object]],
) -> np.ndarray:
    canvas = image.copy()
    palette = [(255, 0, 0), (0, 180, 255), (0, 255, 0), (255, 0, 255), (255, 180, 0)]
    for index, group in enumerate(group_debug):
        color = palette[index % len(palette)] if group["collapsed"] else (128, 128, 128)
        for segment_id in group["member_segment_ids"]:
            segment = segments_by_id.get(segment_id)
            if segment is None:
                continue
            cv2.line(canvas, (segment.x1, segment.y1), (segment.x2, segment.y2), color, 2)
    return canvas


def _build_summary_text(
    image_path: Path,
    contour_count: int,
    raw_contours_found: int,
    shape_count: int,
    node_count: int,
    connector_count: int,
    artifacts_rejected: int,
    internal_noise_rejected: int,
    connector_fragments_found: int,
    connector_paths_merged: int,
    route_count: int,
    graph_sanity_status: str,
    graph_build_metrics: dict[str, int],
    structural_diagnostics: list[str],
    verification: Verification,
) -> str:
    lines = [
        f"source_file: {image_path.name}",
        f"contours_found: {contour_count}",
        f"raw_contours_found: {raw_contours_found}",
        f"shape_candidates_kept: {shape_count}",
        f"canonical_nodes_kept: {node_count}",
        f"connector_candidates_kept: {connector_count}",
        f"artifacts_rejected: {artifacts_rejected}",
        f"internal_noise_rejected: {internal_noise_rejected}",
        f"connector_fragments_found: {connector_fragments_found}",
        f"connector_paths_merged: {connector_paths_merged}",
        f"route_count: {route_count}",
        f"graph_sanity_status: {graph_sanity_status}",
        f"intersections_detected_raw: {graph_build_metrics['intersections_detected_raw']}",
        f"intersections_accepted: {graph_build_metrics['intersections_accepted']}",
        f"segments_split: {graph_build_metrics['segments_split']}",
        f"split_edges_created: {graph_build_metrics['split_edges_created']}",
        f"junction_vertices_created: {graph_build_metrics['junction_vertices_created']}",
        f"verification_status: {verification.status}",
        f"edge_overlap_score: {verification.edge_overlap_score}",
        f"pixel_difference_score: {verification.pixel_difference_score}",
    ]
    lines.extend(f"diagnostic: {diagnostic}" for diagnostic in structural_diagnostics)
    return "\n".join(lines)


def _freeze_canonical_nodes(
    elements: list[Element],
    image_width: int,
    image_height: int,
    params: PipelineParameters,
) -> tuple[list[Node], list[dict[str, object]]]:
    shape_elements = [element for element in elements if element.element_type == "shape_candidate"]
    scored: list[tuple[float, Element, dict[str, object]]] = []
    for element in shape_elements:
        metrics = element.debug.get("separation_metrics", {})
        bbox = element.bbox
        contains_count = 0
        overlaps_count = 0
        for other in shape_elements:
            if other.id == element.id:
                continue
            if bbox_contains(bbox, other.bbox, margin=6):
                contains_count += 1
            if bbox_iou(bbox, other.bbox) > 0.05:
                overlaps_count += 1
        shape_type = element.interpreted_geometry.shape_type
        shape_score = 2.6 if shape_type == "rectangle-like" else 0.9 if shape_type == "polygon-like" else 0.2
        bbox_area = bbox[2] * bbox[3]
        score = (
            shape_score
            + float(metrics.get("bbox_fill_ratio", 0.0))
            + min(float(metrics.get("contour_area", 0)) / 8000.0, 1.2)
            - contains_count * 1.0
            - overlaps_count * 0.4
            - (bbox_area / 40000.0)
        )
        scored.append((score, element, {"contains_count": contains_count, "overlaps_count": overlaps_count, "bbox_area": bbox_area}))

    scored.sort(key=lambda item: (item[0], -item[2]["bbox_area"]), reverse=True)
    nodes: list[Node] = []
    rejected: list[dict[str, object]] = []

    for _, element, debug in scored:
        metrics = element.debug.get("separation_metrics", {})
        shape_type = element.interpreted_geometry.shape_type
        bbox = element.bbox
        if bbox[2] < 24 or bbox[3] < 24:
            rejected.append({"element_id": element.id, "reason": "too_small_for_canonical_node", "bbox": element.bbox})
            continue
        if shape_type != "rectangle-like" and debug["bbox_area"] > 25000:
            rejected.append({"element_id": element.id, "reason": "oversized_non_rectangular_mass", "bbox": element.bbox})
            continue
        if shape_type != "rectangle-like" and float(metrics.get("bbox_fill_ratio", 0.0)) < 0.5 and debug["bbox_area"] > 12000:
            rejected.append({"element_id": element.id, "reason": "large_low_fill_merged_mass", "bbox": element.bbox})
            continue
        if debug["contains_count"] >= 1 and shape_type != "rectangle-like":
            rejected.append({"element_id": element.id, "reason": "contains_multiple_smaller_shapes", "bbox": element.bbox})
            continue
        if debug["overlaps_count"] >= 3 and shape_type != "rectangle-like":
            rejected.append({"element_id": element.id, "reason": "overlaps_many_other_shapes", "bbox": element.bbox})
            continue
        if any(bbox_iou(element.bbox, node.bbox) >= 0.04 or bbox_contains(element.bbox, node.bbox, margin=2) for node in nodes):
            rejected.append({"element_id": element.id, "reason": "overlaps_existing_node", "bbox": element.bbox})
            continue
        if int(metrics.get("contour_area", 0)) < params.min_shape_area:
            rejected.append({"element_id": element.id, "reason": "below_node_area_threshold", "bbox": element.bbox})
            continue
        node = build_node_from_element(
            node_id=f"node_{len(nodes) + 1:03d}",
            element=element,
            image_width=image_width,
            image_height=image_height,
            outward_padding=params.node_outward_padding,
            label_height_ratio=params.node_label_height_ratio,
            gate_min_span=params.node_gate_min_span,
            gate_max_span=params.node_gate_max_span,
        )
        node.debug.update(
            {
                "source_metrics": metrics,
                "bbox_frozen": True,
                "contains_count": debug["contains_count"],
                "overlaps_count": debug["overlaps_count"],
            }
        )
        element.debug["canonical_node_id"] = node.id
        nodes.append(node)

    return nodes, rejected


def _build_connector_objects(snapped_records: list[dict[str, object]]) -> list[Connector]:
    connectors: list[Connector] = []
    for index, record in enumerate(snapped_records, start=1):
        connectors.append(
            build_connector(
                connector_id=f"connector_{index:03d}",
                points=record["points"],
                src_node_id=record["src_node_id"],
                src_side=record["src_side"],
                dst_node_id=record["dst_node_id"],
                dst_side=record["dst_side"],
                confidence=float(record["confidence"]),
                debug=record["debug"],
            )
        )
    return connectors


def _apply_structural_failures(
    verification: Verification,
    diagnostics: list[str],
) -> Verification:
    if not diagnostics:
        return verification
    notes = list(verification.notes) + diagnostics
    return Verification(
        edge_overlap_score=verification.edge_overlap_score,
        pixel_difference_score=verification.pixel_difference_score,
        status="fail",
        notes=notes,
    )


def _normalized_graph_build_metrics(metrics: dict[str, int]) -> dict[str, int]:
    keys = [
        "intersections_candidates_raw",
        "intersections_detected_raw",
        "intersections_accepted_initial",
        "intersections_accepted",
        "segments_split_initial",
        "segments_split",
        "split_edges_created_initial",
        "split_edges_created",
        "junction_vertices_created",
        "max_splits_per_segment",
        "segments_blocked_from_splitting",
    ]
    return {key: int(metrics.get(key, 0)) for key in keys}


def _build_metrics_payload(
    diagram_id: str,
    summary: dict[str, object],
    verification: Verification,
    noise_metrics: dict[str, int],
) -> dict[str, object]:
    payload = {
        "diagram_id": diagram_id,
        "route_count": int(summary.get("route_count", 0)),
        "graph_vertices": int(summary.get("graph_vertices", 0)),
        "graph_edges": int(summary.get("graph_edges", 0)),
        "final_graph_vertices": int(summary.get("final_graph_vertices", 0)),
        "final_graph_edges": int(summary.get("final_graph_edges", 0)),
        "final_graph_junction_vertices": int(summary.get("final_graph_junction_vertices", 0)),
        "final_graph_bend_vertices": int(summary.get("final_graph_bend_vertices", 0)),
        "final_graph_endpoint_vertices": int(summary.get("final_graph_endpoint_vertices", 0)),
        "verification_status": verification.status,
        "edge_overlap_score": float(verification.edge_overlap_score),
        "pixel_difference_score": float(verification.pixel_difference_score),
        "intersections_detected_raw": int(summary.get("intersections_detected_raw", 0)),
        "intersections_accepted_initial": int(summary.get("intersections_accepted_initial", 0)),
        "intersections_accepted": int(summary.get("intersections_accepted", 0)),
        "segments_split_initial": int(summary.get("segments_split_initial", 0)),
        "segments_split": int(summary.get("segments_split", 0)),
        "split_edges_created_initial": int(summary.get("split_edges_created_initial", 0)),
        "split_edges_created": int(summary.get("split_edges_created", 0)),
        "junction_vertices_created": int(summary.get("junction_vertices_created", 0)),
        "max_splits_per_segment": int(summary.get("max_splits_per_segment", 0)),
        "segments_blocked_from_splitting": int(summary.get("segments_blocked_from_splitting", 0)),
        "degree2_endpoints_reclassified": int(summary.get("degree2_endpoints_reclassified", 0)),
        "gate_stubs_absorbed": int(summary.get("gate_stubs_absorbed", 0)),
        "micro_bends_removed": int(summary.get("micro_bends_removed", 0)),
        "corridor_contacts_snapped": int(summary.get("corridor_contacts_snapped", 0)),
    }
    payload.update(noise_metrics)
    return payload


def _stabilized_graph_build_metrics(
    vertices: list[object],
    edges: list[object],
    crossings: list[dict[str, object]],
    raw_metrics: dict[str, int],
) -> dict[str, int]:
    vertex_points = {(int(vertex.x), int(vertex.y)) for vertex in vertices}
    split_edges = [edge for edge in edges if edge.debug.get("split_from_intersection")]
    segments_split = len({edge.debug.get("source_segment_id") for edge in split_edges if edge.debug.get("source_segment_id")})
    per_segment_split_counts: dict[str, int] = {}
    for edge in split_edges:
        source_segment_id = edge.debug.get("source_segment_id")
        if source_segment_id is None:
            continue
        per_segment_split_counts[source_segment_id] = per_segment_split_counts.get(source_segment_id, 0) + 1
    return {
        "intersections_candidates_raw": int(raw_metrics.get("intersections_candidates_raw", 0)),
        "intersections_detected_raw": int(raw_metrics.get("intersections_detected_raw", 0)),
        "intersections_accepted_initial": int(raw_metrics.get("intersections_accepted", 0)),
        "segments_split_initial": int(raw_metrics.get("segments_split", 0)),
        "split_edges_created_initial": int(raw_metrics.get("split_edges_created", 0)),
        "intersections_accepted": sum(1 for crossing in crossings if tuple(crossing["point"]) in vertex_points),
        "segments_split": segments_split,
        "split_edges_created": len(edges),
        "junction_vertices_created": sum(1 for vertex in vertices if vertex.kind == "junction"),
        "max_splits_per_segment": max(per_segment_split_counts.values(), default=0),
        "segments_blocked_from_splitting": int(raw_metrics.get("segments_blocked_from_splitting", 0)),
    }


def summarize_noise_metrics(
    *,
    separation_summary: dict[str, object],
    rejected_node_candidates: list[dict[str, object]],
    graph_build_metrics_raw: dict[str, object],
    spurs_pruned: int,
    gate_relevant_components_kept: int,
) -> dict[str, int]:
    intersections_detected_raw = int(graph_build_metrics_raw.get("intersections_detected_raw", 0))
    intersections_accepted_initial = int(graph_build_metrics_raw.get("intersections_accepted", 0))
    return {
        "noise_artifacts_rejected": int(separation_summary.get("artifacts_rejected", 0)),
        "noise_internal_rejected": int(separation_summary.get("internal_noise_rejected", 0)),
        "noise_node_candidates_rejected": len(rejected_node_candidates),
        "noise_segments_filtered_pre_intersection": int(graph_build_metrics_raw.get("segments_blocked_from_splitting", 0)),
        "noise_intersections_rejected": max(intersections_detected_raw - intersections_accepted_initial, 0),
        "noise_spurs_pruned": int(spurs_pruned),
        "noise_final_components_pruned": int(gate_relevant_components_kept),
    }


def process_image(image_path: Path, outputs_root: Path) -> ProcessingSummary:
    run_simplification_self_test()
    params = PipelineParameters()
    output_dir = outputs_root / image_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    color, grayscale = load_image(image_path)
    write_image(output_dir, "01_original.png", color)
    write_image(output_dir, "02_grayscale.png", grayscale)

    normalized = normalize_image(
        grayscale=grayscale,
        blur_kernel_size=params.blur_kernel_size,
        clahe_clip_limit=params.clahe_clip_limit,
        clahe_grid_size=params.clahe_grid_size,
        adaptive_block_size=params.adaptive_block_size,
        adaptive_c=params.adaptive_c,
    )
    normalized_grayscale = normalized["normalized_grayscale"]
    binary = normalized["binary"]
    write_image(output_dir, "03_normalized.png", normalized_grayscale)
    write_image(output_dir, "03b_binary.png", binary)

    edges = detect_edges(
        normalized_grayscale=normalized_grayscale,
        canny_low=params.canny_low,
        canny_high=params.canny_high,
        aperture_size=params.canny_aperture_size,
    )
    write_image(output_dir, "04_edges.png", edges)

    separation = separate_geometry(
        binary=binary,
        edges=edges,
        shape_close_kernel_size=params.shape_close_kernel_size,
        shape_dilate_kernel_size=params.shape_dilate_kernel_size,
        min_shape_area=params.min_shape_area,
        max_shape_area_ratio=params.max_shape_area_ratio,
        artifact_border_margin=params.artifact_border_margin,
        artifact_border_touch_reject_count=params.artifact_border_touch_reject_count,
        artifact_extreme_span_ratio=params.artifact_extreme_span_ratio,
        artifact_frame_fill_ratio_threshold=params.artifact_frame_fill_ratio_threshold,
        internal_containment_margin=params.internal_containment_margin,
        internal_small_box_area_limit=params.internal_small_box_area_limit,
        internal_text_like_max_height=params.internal_text_like_max_height,
        internal_text_like_aspect_ratio=params.internal_text_like_aspect_ratio,
        internal_child_area_ratio_threshold=params.internal_child_area_ratio_threshold,
        internal_child_bbox_area_ratio_threshold=params.internal_child_bbox_area_ratio_threshold,
    )
    write_image(output_dir, "04a_shape_mask.png", separation.shape_mask)
    write_image(output_dir, "04b_line_mask.png", separation.line_mask)
    write_image(output_dir, "04c_artifact_mask.png", separation.artifact_mask)
    write_image(output_dir, "05h_shapes_subtracted_for_line_recovery.png", separation.shapes_subtracted_mask)

    provisional_elements, contours, _ = extract_primitives(
        shape_candidates=separation.shape_candidates,
        connector_paths=[],
        connector_group_ids=[],
        min_contour_area=params.min_contour_area,
        contour_epsilon_ratio=params.contour_epsilon_ratio,
        min_connector_path_length=params.connector_min_merged_path_length,
    )

    nodes, rejected_node_candidates = _freeze_canonical_nodes(
        elements=provisional_elements,
        image_width=color.shape[1],
        image_height=color.shape[0],
        params=params,
    )
    node_ids = {node.id for node in nodes}
    elements = [
        element
        for element in provisional_elements
        if element.debug.get("canonical_node_id") in node_ids
    ]

    protected_node_mask, gate_mask = build_protected_node_mask(
        image_width=color.shape[1],
        image_height=color.shape[0],
        nodes=nodes,
        inward_padding=params.node_inward_padding,
        gate_padding=params.node_gate_padding,
    )
    connector_space = connector_space_from_masks(separation.line_mask, protected_node_mask, gate_mask)

    write_image(output_dir, "05_contours.png", overlay_interpretation(color, provisional_elements))
    write_image(output_dir, "05a_shapes_overlay.png", overlay_interpretation(color, elements))
    write_image(output_dir, "05c_shape_candidates_before_internal_filter.png", _draw_candidate_overlay(color, separation.shape_candidates_before_filter, (255, 0, 0)))
    write_image(output_dir, "05d_shape_candidates_after_internal_filter.png", _draw_candidate_overlay(color, separation.shape_candidates, (0, 200, 0)))
    write_image(output_dir, "05e_internal_noise_rejected.png", _draw_candidate_overlay(color, separation.internal_noise_candidates, (0, 0, 255)))

    write_image(output_dir, "06a_canonical_nodes.png", overlay_nodes(color, nodes))
    write_image(output_dir, "06b_node_protection_mask.png", protected_node_mask)
    write_image(output_dir, "06c_attachment_gates.png", overlay_gates(color, nodes))
    write_image(output_dir, "06d_connector_space.png", connector_space)

    connector_fragments = extract_connector_fragments(
        line_mask=connector_space,
        hough_threshold=params.connector_hough_threshold,
        min_line_length=params.connector_min_line_length,
        max_line_gap=params.connector_max_line_gap,
        orientation_tolerance=params.connector_orientation_tolerance,
    )
    write_image(output_dir, "05f_connector_fragments_overlay.png", _draw_lines(color, [fragment.points for fragment in connector_fragments], (255, 128, 0)))
    write_image(output_dir, "06e_connector_fragments_protected.png", _draw_lines(color, [fragment.points for fragment in connector_fragments], (255, 128, 0)))

    connector_paths, connector_group_ids = merge_connector_fragments(
        fragments=connector_fragments,
        endpoint_gap_threshold=params.connector_merge_gap_threshold,
        collinear_angle_tolerance=params.connector_merge_angle_tolerance,
        min_merged_path_length=params.connector_min_merged_path_length,
    )
    write_image(output_dir, "05g_connector_paths_merged.png", _draw_lines(color, connector_paths, (0, 255, 255)))

    ortho_paths = orthogonalize_paths(
        connector_paths,
        orth_axis_tolerance=params.graph_orth_axis_tolerance,
        spur_min_length=params.graph_spur_min_length,
    )
    working_segments = build_ortho_segments(ortho_paths)
    ortho_segments_initial = list(working_segments)
    segments_raw = len(working_segments)
    working_segments = normalize_ortho_segments(
        working_segments,
        axis_snap_tolerance=params.simplify_axis_snap_tolerance,
    )
    ortho_segments_normalized = list(working_segments)
    working_segments = iterative_collinear_merge(
        working_segments,
        merge_gap_tolerance=params.simplify_merge_gap_tolerance,
        parallel_offset_tolerance=params.simplify_parallel_offset_tolerance,
    )
    ortho_segments_merged = list(working_segments)
    segments_after_collinear_merge = len(working_segments)
    corridor_debug_input = {segment.id: segment for segment in working_segments}
    working_segments, corridor_groups_collapsed, corridor_group_debug = collapse_parallel_corridors(
        working_segments,
        overlap_ratio_min=params.corridor_overlap_ratio_min,
        parallel_distance_max=params.corridor_parallel_distance_max,
        min_group_size=params.corridor_min_group_size,
    )
    ortho_segments_collapsed = list(working_segments)
    if corridor_groups_collapsed == 0:
        raise RuntimeError("Corridor collapse did not execute")
    segments_after_corridor_grouping = len(corridor_group_debug)
    segments_after_corridor_collapse = len(working_segments)
    if segments_after_corridor_collapse >= segments_after_collinear_merge and corridor_groups_collapsed == 0:
        raise RuntimeError("corridor_collapse_no_effect")
    working_segments = filter_dominant_segments(
        working_segments,
        parallel_offset_tolerance=params.simplify_parallel_offset_tolerance,
    )
    ortho_segments_dominant = list(working_segments)
    segments_after_dominance_filter = len(working_segments)
    gate_points = [point for node in nodes for point in node.gates.values()]
    working_segments, spurs_pruned = prune_spurs(
        working_segments,
        gate_points=gate_points,
        spur_prune_length=params.spur_prune_length,
    )
    graph_input_segments = working_segments
    assert graph_input_segments is working_segments
    write_image(output_dir, "07a_connector_skeleton.png", connector_space)
    write_image(output_dir, "07b_connector_centerlines.png", _draw_lines(color, ortho_paths, (255, 180, 0)))
    write_image(output_dir, "07c1_primitives_normalized.png", overlay_segments(color, ortho_segments_normalized, (0, 180, 255)))
    write_image(output_dir, "07c2_collinear_segments_merged.png", overlay_segments(color, ortho_segments_merged, (0, 220, 255)))
    write_image(output_dir, "07c3_corridors_collapsed.png", overlay_segments(color, ortho_segments_collapsed, (0, 255, 255)))
    write_image(output_dir, "07c3b_corridor_group_debug.png", _draw_corridor_group_debug(color, corridor_debug_input, corridor_group_debug))
    write_image(output_dir, "07c4_spurs_pruned.png", overlay_segments(color, graph_input_segments, (0, 255, 180)))
    write_image(output_dir, "07c_orthogonal_segments.png", overlay_segments(color, graph_input_segments, (0, 255, 255)))

    graph_vertices, graph_edges, crossing_debug, graph_build_metrics_raw = build_graph(
        segments=graph_input_segments,
        connector_space=connector_space,
        continuity_radius=params.graph_intersection_continuity_radius,
        endpoint_intersection_tolerance=params.graph_endpoint_intersection_tolerance,
    )
    graph_build_metrics = _normalized_graph_build_metrics(graph_build_metrics_raw)
    graph_vertices_before_degree2 = len(graph_vertices)
    graph_vertices, graph_edges, degree2_vertices_removed, degree2_candidate_count = reduce_degree2_vertices(graph_vertices, graph_edges)
    graph_vertices_after_degree2 = len(graph_vertices)
    if graph_vertices_before_degree2 == graph_vertices_after_degree2 and degree2_candidate_count > 10:
        raise RuntimeError("degree2_compression_no_effect")
    if any(edge.debug.get("source_segment_stage") != "collapsed_segments" for edge in graph_edges):
        raise RuntimeError("graph_built_from_unsimplified_segments")
    write_image(output_dir, "07d_graph_vertices.png", overlay_vertices(color, graph_vertices))
    write_image(output_dir, "07d1_graph_vertices_reduced.png", overlay_vertices(color, graph_vertices))
    write_image(output_dir, "07e_connector_graph.png", overlay_graph(color, graph_vertices, graph_edges))

    graph_vertices, graph_edges, gate_attachments, gate_cleanup_metrics = attach_gates_to_graph(
        nodes=nodes,
        segments=graph_input_segments,
        vertices=graph_vertices,
        edges=graph_edges,
        attach_tolerance=params.graph_gate_attach_tolerance,
        micro_bend_threshold=params.graph_micro_bend_threshold,
    )
    graph_vertices, graph_edges, gate_relevant_components_kept = filter_graph_to_gate_reachable(
        vertices=graph_vertices,
        edges=graph_edges,
        seed_vertex_ids=[attachment["graph_vertex_id"] for attachment in gate_attachments],
    )
    graph_vertices, graph_edges, degree2_removed_reachable, _ = reduce_degree2_vertices(graph_vertices, graph_edges)
    degree2_vertices_removed += degree2_removed_reachable
    gate_cleanup_metrics["degree2_vertices_removed_post_attach"] += degree2_removed_reachable
    write_image(output_dir, "07e1_gate_relevant_graph.png", overlay_graph(color, graph_vertices, graph_edges))
    write_image(output_dir, "07f_gate_graph_attachments.png", overlay_graph(color, graph_vertices, graph_edges))

    simplified_paths_for_routing = [[(segment.x1, segment.y1), (segment.x2, segment.y2)] for segment in graph_input_segments]
    routes = route_recovered_paths_via_graph(
        ortho_paths=simplified_paths_for_routing,
        attachments=gate_attachments,
        vertices=graph_vertices,
        edges=graph_edges,
        endpoint_tolerance=params.graph_gate_attach_tolerance,
        micro_bend_threshold=params.graph_micro_bend_threshold,
        axis_snap_tolerance=params.simplify_axis_snap_tolerance,
    )
    write_image(output_dir, "07g_routed_connectors.png", _draw_lines(color, [route.points for route in routes], (0, 255, 0)))
    write_image(output_dir, "07g1_routes_from_simplified_graph.png", _draw_lines(color, [route.points for route in routes], (0, 255, 0)))

    snapped_records, endpoint_candidates, snapped_paths = snap_connector_endpoints_to_nodes(
        paths=[route.points for route in routes],
        nodes=nodes,
        snap_distance_tolerance=params.connector_snap_distance_tolerance,
        directional_axis_ratio=params.connector_directional_axis_ratio,
    )
    write_image(output_dir, "06f_endpoint_candidates.png", _draw_points(color, endpoint_candidates, (0, 0, 255)))
    write_image(output_dir, "06g_snapped_connectors.png", _draw_lines(color, snapped_paths, (0, 255, 255)))

    connectors = _build_connector_objects(snapped_records)
    for connector in connectors:
        min_x = min(point[0] for point in connector.points)
        min_y = min(point[1] for point in connector.points)
        max_x = max(point[0] for point in connector.points)
        max_y = max(point[1] for point in connector.points)
        elements.append(
            Element(
                id=connector.id,
                element_type="connector_candidate",
                raw_geometry=RawGeometry(path_points=connector.points, perimeter=0),
                interpreted_geometry=InterpretedGeometry(path_type="polyline", render_points=connector.points, closed=False),
                bbox=(min_x, min_y, max_x - min_x, max_y - min_y),
                center=(int(round((min_x + max_x) / 2)), int(round((min_y + max_y) / 2))),
                confidence=connector.confidence,
                debug={
                    "source_mask": "protected_connector_space",
                    "src_node_id": connector.src_node_id,
                    "dst_node_id": connector.dst_node_id,
                    "src_side": connector.src_side,
                    "dst_side": connector.dst_side,
                    **connector.debug,
                },
            )
        )

    rendered_connectors = [connector for connector in connectors if connector.src_node_id and connector.dst_node_id]
    rendered_structural = render_structure(
        color.shape[1],
        color.shape[0],
        nodes,
        rendered_connectors or connectors,
    )
    write_image(output_dir, "07h_rendered_graph_structure.png", rendered_structural)
    write_image(output_dir, "07h1_rendered_simplified_graph_structure.png", rendered_structural)
    write_image(output_dir, "07_rendered_structural.png", rendered_structural)
    write_image(output_dir, "07_rendered.png", rendered_structural)

    verification, diff_image = verify_render(
        normalized_binary=binary,
        rendered_image=rendered_structural,
        edge_overlap_pass=params.edge_overlap_pass,
        edge_overlap_warn=params.edge_overlap_warn,
        pixel_diff_pass=params.pixel_diff_pass,
        pixel_diff_warn=params.pixel_diff_warn,
        canny_low=params.canny_low,
        canny_high=params.canny_high,
        aperture_size=params.canny_aperture_size,
    )

    structural_diagnostics: list[str] = []
    if len(nodes) < params.expected_min_nodes:
        structural_diagnostics.append(f"fewer_than_expected_nodes:{len(nodes)}")
    for i, first in enumerate(nodes):
        for second in nodes[i + 1 :]:
            if bbox_iou(first.bbox, second.bbox) > 0.05:
                structural_diagnostics.append(f"overlapping_nodes:{first.id}:{second.id}")
    if image_path.stem == "Diagram1":
        if corridor_groups_collapsed <= 0:
            structural_diagnostics.append("diagram1_expected_corridor_collapse_missing")
        if len(routes) < 3:
            structural_diagnostics.append("diagram1_route_count_below_expected")

    graph_vertices, graph_edges = filter_graph_to_routes(
        vertices=graph_vertices,
        edges=graph_edges,
        routes=routes,
    )
    final_graph_summary = summarize_final_graph(graph_vertices, graph_edges)
    graph_build_metrics = _stabilized_graph_build_metrics(
        graph_vertices,
        graph_edges,
        crossing_debug,
        graph_build_metrics_raw,
    )
    graph_diag = graph_sanity(
        vertices=graph_vertices,
        edges=graph_edges,
        reduced_degree2_vertices=degree2_vertices_removed,
        pruned_spurs=spurs_pruned,
        collapsed_corridor_groups=corridor_groups_collapsed,
        warn_vertices=params.graph_vertices_warn,
        fail_vertices=params.graph_vertices_fail,
        warn_edges=params.graph_edges_warn,
        fail_edges=params.graph_edges_fail,
    )
    if graph_diag.status == "fail":
        structural_diagnostics.append("graph_over_fragmented")
    elif graph_diag.status == "warn":
        structural_diagnostics.append("graph_still_dense")
    if image_path.stem == "Diagram1" and len(graph_vertices) >= 55:
        structural_diagnostics.append("diagram1_graph_vertices_above_expected_limit")

    verification = _apply_structural_failures(verification, structural_diagnostics)
    if not routes:
        structural_diagnostics.append("no_graph_routes_found")
    write_image(output_dir, "08_diff_structural.png", diff_image)
    write_image(output_dir, "08b_diff_graph_structure.png", diff_image)
    write_image(output_dir, "08c_diff_simplified_graph_structure.png", diff_image)
    write_image(output_dir, "08_diff.png", diff_image)

    noise_metrics = summarize_noise_metrics(
        separation_summary=separation.summary,
        rejected_node_candidates=rejected_node_candidates,
        graph_build_metrics_raw=graph_build_metrics_raw,
        spurs_pruned=spurs_pruned,
        gate_relevant_components_kept=gate_relevant_components_kept,
    )

    metadata = {
        "diagram_metadata": {
            "source_file": image_path.name,
            "image_width": int(color.shape[1]),
            "image_height": int(color.shape[0]),
            "channels": int(color.shape[2]),
        },
        "separation_debug": {
            "rejected_artifacts": [
                {"rejection_reason": candidate.rejection_reason, "metrics": candidate.metrics}
                for candidate in separation.rejected_candidates
            ],
            "internal_noise_rejected": [
                {
                    "rejection_reason": candidate.rejection_reason,
                    "metrics": candidate.metrics,
                    "parent_shape_id": candidate.parent_shape_id,
                }
                for candidate in separation.internal_noise_candidates
            ],
            "rejected_node_candidates": rejected_node_candidates,
        },
        "structural_render": {
            "uses_canonical_nodes_only": True,
            "uses_snapped_connectors_only": False,
            "uses_graph_routed_connectors_only": True,
            "fallback_to_contours": False,
            "diagnostics": structural_diagnostics,
        },
        "graph_sanity": graph_diag.to_dict(),
        "graph_counter_stages": {
            "intersections_accepted_initial": "accepted intersections before graph cleanup and route-relevant export filtering",
            "segments_split_initial": "segments split before graph cleanup and route-relevant export filtering",
            "split_edges_created_initial": "split edges created before graph cleanup and route-relevant export filtering",
            "final_graph_vertices": "count of exported graph.vertices",
            "final_graph_edges": "count of exported graph.edges",
            "final_graph_junction_vertices": "exported graph vertices with degree >= 3",
            "final_graph_bend_vertices": "exported graph vertices with degree == 2",
            "final_graph_endpoint_vertices": "exported graph vertices with degree == 1",
            "intersections_accepted": "legacy alias for final exported graph crossing points",
            "junction_vertices_created": "legacy alias for final_graph_junction_vertices",
        },
        "noise_metrics": noise_metrics,
    }
    separation_summary = dict(separation.summary)
    separation_summary["connector_fragments_found"] = len(connector_fragments)
    separation_summary["connector_paths_merged"] = len(connector_paths)
    separation_summary["canonical_nodes_kept"] = len(nodes)
    separation_summary["segments_raw"] = segments_raw
    separation_summary["segments_before_simplification"] = len(ortho_segments_initial)
    separation_summary["segments_after_collinear_merge"] = len(ortho_segments_merged)
    separation_summary["segments_after_corridor_grouping"] = segments_after_corridor_grouping
    separation_summary["segments_after_corridor_collapse"] = segments_after_corridor_collapse
    separation_summary["segments_after_dominance_filter"] = segments_after_dominance_filter
    separation_summary["corridor_groups_collapsed"] = corridor_groups_collapsed
    separation_summary["spurs_pruned"] = spurs_pruned
    separation_summary["degree2_vertices_removed"] = degree2_vertices_removed
    separation_summary["degree2_endpoints_reclassified"] = gate_cleanup_metrics["degree2_endpoints_reclassified"]
    separation_summary["gate_stubs_absorbed"] = gate_cleanup_metrics["gate_stubs_absorbed"]
    separation_summary["micro_bends_removed"] = gate_cleanup_metrics["micro_bends_removed"]
    separation_summary["corridor_contacts_snapped"] = gate_cleanup_metrics["corridor_contacts_snapped"]
    separation_summary["degree2_vertices_removed_post_attach"] = gate_cleanup_metrics["degree2_vertices_removed_post_attach"]
    separation_summary["graph_vertices_before_degree2"] = graph_vertices_before_degree2
    separation_summary["graph_vertices_after_degree2"] = graph_vertices_after_degree2
    separation_summary["gate_relevant_components_kept"] = gate_relevant_components_kept
    separation_summary["graph_vertices"] = final_graph_summary["final_graph_vertices"]
    separation_summary["graph_edges"] = final_graph_summary["final_graph_edges"]
    separation_summary["route_count"] = len(routes)
    separation_summary["graph_sanity_status"] = graph_diag.status
    separation_summary.update(graph_build_metrics)
    separation_summary.update(final_graph_summary)
    metrics_payload = _build_metrics_payload(image_path.stem, separation_summary, verification, noise_metrics)

    document = DiagramDocument(
        schema_version="1.0.0",
        diagram_id=image_path.stem,
        source_file=image_path.name,
        image_width=int(color.shape[1]),
        image_height=int(color.shape[0]),
        metadata=metadata,
        processing_parameters=asdict(params),
        separation_summary=separation_summary,
        elements=elements,
        nodes=nodes,
        connectors=connectors,
        routes=routes,
        graph={
            "vertices": [vertex.to_dict() for vertex in graph_vertices],
            "edges": [edge.to_dict() for edge in graph_edges],
            "segments": [segment.to_dict() for segment in graph_input_segments],
            "gate_attachments": gate_attachments,
            "crossings": crossing_debug,
            "build_metrics": graph_build_metrics,
            "intersections_rejected_by_reason": graph_build_metrics_raw.get("intersections_rejected_by_reason", {}),
            "diagnostics": graph_diag.to_dict(),
            "corridor_group_debug": corridor_group_debug,
        },
        verification=verification,
    )
    export_document(document, output_dir / "diagram.json")
    write_json(output_dir, "metrics.json", metrics_payload)

    write_text(
        output_dir,
        "summary.txt",
        _build_summary_text(
            image_path=image_path,
            contour_count=len(contours),
            raw_contours_found=separation.summary["raw_contours_found"],
            shape_count=len([element for element in elements if element.element_type == "shape_candidate"]),
            node_count=len(nodes),
            connector_count=len(connectors),
            artifacts_rejected=separation.summary["artifacts_rejected"],
            internal_noise_rejected=separation.summary["internal_noise_rejected"],
            connector_fragments_found=len(connector_fragments),
            connector_paths_merged=len(connector_paths),
            route_count=len(routes),
            graph_sanity_status=graph_diag.status,
            graph_build_metrics=graph_build_metrics,
            structural_diagnostics=structural_diagnostics,
            verification=verification,
        ),
    )

    return ProcessingSummary(
        image_name=image_path.name,
        element_count=len(elements),
        contour_count=len(contours),
        connector_count=len(connectors),
        verification_status=verification.status,
    )

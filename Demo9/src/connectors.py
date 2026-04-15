from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from .grid import snap_point, snap_points
from .models import Node


Point = tuple[int, int]


@dataclass
class ConnectorFragment:
    points: list[Point]
    length: float
    angle: float
    bbox: tuple[int, int, int, int]


def _segment_length(points: list[Point]) -> float:
    return math.dist(points[0], points[-1])


def _segment_angle(points: list[Point]) -> float:
    dx = points[-1][0] - points[0][0]
    dy = points[-1][1] - points[0][1]
    return math.degrees(math.atan2(dy, dx))


def _bbox(points: list[Point]) -> tuple[int, int, int, int]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    return min_x, min_y, max_x - min_x, max_y - min_y


def _orientation_bucket(angle: float, slanted_angle_tolerance: float) -> str:
    normalized = abs(angle) % 180.0
    if normalized <= slanted_angle_tolerance or abs(normalized - 180.0) <= slanted_angle_tolerance:
        return "horizontal"
    if abs(normalized - 90.0) <= slanted_angle_tolerance:
        return "vertical"
    return "slanted"


def extract_connector_fragments(
    line_mask: np.ndarray,
    hough_threshold: int,
    min_line_length: int,
    max_line_gap: int,
    orientation_tolerance: float,
) -> list[ConnectorFragment]:
    segments = cv2.HoughLinesP(
        line_mask,
        1,
        np.pi / 180,
        threshold=hough_threshold,
        minLineLength=min_line_length,
        maxLineGap=max_line_gap,
    )
    if segments is None:
        return []

    fragments: list[ConnectorFragment] = []
    for segment in segments:
        coords = segment.reshape(-1, 2)
        points = [snap_point((int(coords[0][0]), int(coords[0][1]))), snap_point((int(coords[1][0]), int(coords[1][1])))]
        length = _segment_length(points)
        if length < min_line_length:
            continue
        angle = _segment_angle(points)
        fragments.append(
            ConnectorFragment(
                points=points,
                length=length,
                angle=angle,
                bbox=_bbox(points),
            )
        )

    unique_fragments: list[ConnectorFragment] = []
    for fragment in fragments:
        is_duplicate = False
        for existing in unique_fragments:
            if (
                _orientation_bucket(fragment.angle, orientation_tolerance)
                == _orientation_bucket(existing.angle, orientation_tolerance)
                and math.dist(fragment.points[0], existing.points[0]) <= 6
                and math.dist(fragment.points[-1], existing.points[-1]) <= 6
            ):
                is_duplicate = True
                break
        if not is_duplicate:
            unique_fragments.append(fragment)
    return unique_fragments


def _normalize_direction(points: list[Point]) -> list[Point]:
    return points if points[0] <= points[-1] else list(reversed(points))


def _can_merge(
    first: list[Point],
    second: list[Point],
    endpoint_gap_threshold: int,
    collinear_angle_tolerance: float,
) -> bool:
    first_angle = _segment_angle(first)
    second_angle = _segment_angle(second)
    angle_delta = abs(first_angle - second_angle)
    angle_delta = min(angle_delta, abs(angle_delta - 180.0))
    if angle_delta > collinear_angle_tolerance:
        return False

    endpoint_pairs = [
        (first[0], second[0]),
        (first[0], second[-1]),
        (first[-1], second[0]),
        (first[-1], second[-1]),
    ]
    if min(math.dist(a, b) for a, b in endpoint_pairs) <= endpoint_gap_threshold:
        return True

    first_box = _bbox(first)
    second_box = _bbox(second)
    overlap_x = min(first_box[0] + first_box[2], second_box[0] + second_box[2]) - max(first_box[0], second_box[0])
    overlap_y = min(first_box[1] + first_box[3], second_box[1] + second_box[3]) - max(first_box[1], second_box[1])
    return overlap_x >= -endpoint_gap_threshold or overlap_y >= -endpoint_gap_threshold


def _merge_two_paths(first: list[Point], second: list[Point]) -> list[Point]:
    candidates = [
        _normalize_direction(first) + _normalize_direction(second),
        _normalize_direction(first) + list(reversed(_normalize_direction(second))),
        list(reversed(_normalize_direction(first))) + _normalize_direction(second),
        list(reversed(_normalize_direction(first))) + list(reversed(_normalize_direction(second))),
    ]
    best = min(candidates, key=lambda path: sum(math.dist(path[i], path[i + 1]) for i in range(len(path) - 1)))
    merged: list[Point] = []
    for point in best:
        snapped = snap_point(point)
        if not merged or merged[-1] != snapped:
            merged.append(snapped)
    return merged


def merge_connector_fragments(
    fragments: list[ConnectorFragment],
    endpoint_gap_threshold: int,
    collinear_angle_tolerance: float,
    min_merged_path_length: int,
) -> tuple[list[list[Point]], list[int]]:
    paths = [_normalize_direction(fragment.points) for fragment in fragments]
    merge_group_ids = list(range(1, len(paths) + 1))

    changed = True
    while changed:
        changed = False
        for i in range(len(paths)):
            if changed:
                break
            for j in range(i + 1, len(paths)):
                if _can_merge(paths[i], paths[j], endpoint_gap_threshold, collinear_angle_tolerance):
                    paths[i] = _merge_two_paths(paths[i], paths[j])
                    merge_group_ids[i] = min(merge_group_ids[i], merge_group_ids[j])
                    del paths[j]
                    del merge_group_ids[j]
                    changed = True
                    break

    merged_paths: list[list[Point]] = []
    kept_group_ids: list[int] = []
    for path, group_id in zip(paths, merge_group_ids):
        length = sum(math.dist(path[i], path[i + 1]) for i in range(len(path) - 1))
        if length < min_merged_path_length:
            continue
        merged_paths.append(path)
        kept_group_ids.append(group_id)
    return merged_paths, kept_group_ids


def build_protected_node_mask(
    image_width: int,
    image_height: int,
    nodes: list[Node],
    inward_padding: int,
    gate_padding: int,
) -> tuple[np.ndarray, np.ndarray]:
    protected_mask = np.zeros((image_height, image_width), dtype=np.uint8)
    gate_mask = np.zeros((image_height, image_width), dtype=np.uint8)

    for node in nodes:
        x, y, w, h = node.bbox
        ex, ey, ew, eh = node.expanded_bbox
        cv2.rectangle(protected_mask, (ex, ey), (ex + ew, ey + eh), 255, thickness=cv2.FILLED)
        inner_x = min(max(x + inward_padding, 0), image_width - 1)
        inner_y = min(max(y + inward_padding, 0), image_height - 1)
        inner_w = max(w - 2 * inward_padding, 1)
        inner_h = max(h - 2 * inward_padding, 1)
        cv2.rectangle(
            protected_mask,
            (inner_x, inner_y),
            (min(inner_x + inner_w, image_width - 1), min(inner_y + inner_h, image_height - 1)),
            255,
            thickness=cv2.FILLED,
        )

        for segment in node.gate_segments.values():
            p1, p2 = segment
            cv2.line(gate_mask, p1, p2, 255, thickness=max(1, gate_padding))

    protected_mask = cv2.bitwise_and(protected_mask, cv2.bitwise_not(gate_mask))
    return protected_mask, gate_mask


def connector_space_from_masks(line_mask: np.ndarray, protected_node_mask: np.ndarray, gate_mask: np.ndarray) -> np.ndarray:
    outside_nodes = cv2.bitwise_and(line_mask, cv2.bitwise_not(protected_node_mask))
    return cv2.bitwise_or(outside_nodes, gate_mask)


def _endpoint_direction(path: list[Point], at_start: bool) -> tuple[float, float]:
    if len(path) < 2:
        return (0.0, 0.0)
    if at_start:
        origin, target = path[0], path[1]
    else:
        origin, target = path[-1], path[-2]
    return float(origin[0] - target[0]), float(origin[1] - target[1])


def _direction_compatible(side: str, direction: tuple[float, float], min_axis_ratio: float) -> bool:
    dx, dy = direction
    abs_dx = abs(dx)
    abs_dy = abs(dy)
    if side in {"left", "right"}:
        return abs_dx >= max(1.0, abs_dy * min_axis_ratio)
    return abs_dy >= max(1.0, abs_dx * min_axis_ratio)


def snap_connector_endpoints_to_nodes(
    paths: list[list[Point]],
    nodes: list[Node],
    snap_distance_tolerance: int,
    directional_axis_ratio: float,
) -> tuple[list[dict[str, object]], list[Point], list[list[Point]]]:
    snapped_records: list[dict[str, object]] = []
    endpoint_candidates: list[Point] = []
    snapped_paths: list[list[Point]] = []

    gate_records: list[dict[str, object]] = []
    for node in nodes:
        for side, point in node.gates.items():
            gate_records.append({"node_id": node.id, "side": side, "point": point})

    for path in paths:
        if len(path) < 2:
            continue
        snapped_path = snap_points(path)
        endpoint_candidates.extend([snapped_path[0], snapped_path[-1]])
        attachments: list[dict[str, object] | None] = []

        for at_start in (True, False):
            endpoint = snapped_path[0] if at_start else snapped_path[-1]
            direction = _endpoint_direction(snapped_path, at_start)
            matches: list[tuple[float, dict[str, object]]] = []
            for gate in gate_records:
                distance = math.dist(endpoint, gate["point"])
                if distance > 0 and not _direction_compatible(str(gate["side"]), direction, directional_axis_ratio):
                    continue
                if distance <= snap_distance_tolerance:
                    matches.append((distance, gate))
            if matches:
                matches.sort(key=lambda item: item[0])
                distance, gate = matches[0]
                snapped_point = snap_point(gate["point"])
                if at_start:
                    snapped_path[0] = snapped_point
                else:
                    snapped_path[-1] = snapped_point
                attachments.append(
                    {
                        "node_id": gate["node_id"],
                        "side": gate["side"],
                        "distance": round(distance, 2),
                        "snapped": True,
                    }
                )
            else:
                attachments.append(None)

        snapped_paths.append(snapped_path)
        src_attachment = attachments[0]
        dst_attachment = attachments[1]
        attachment_count = sum(1 for item in attachments if item is not None)
        confidence = 0.45 + 0.2 * attachment_count
        snapped_records.append(
            {
                "points": snapped_path,
                "src_node_id": None if src_attachment is None else src_attachment["node_id"],
                "src_side": None if src_attachment is None else src_attachment["side"],
                "dst_node_id": None if dst_attachment is None else dst_attachment["node_id"],
                "dst_side": None if dst_attachment is None else dst_attachment["side"],
                "confidence": min(confidence, 0.95),
                "debug": {
                    "src_attachment": src_attachment,
                    "dst_attachment": dst_attachment,
                    "orphan": attachment_count == 0,
                },
            }
        )

    return snapped_records, endpoint_candidates, snapped_paths

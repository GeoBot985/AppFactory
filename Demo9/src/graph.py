from __future__ import annotations

import math
from collections import defaultdict, deque

import cv2
import numpy as np

from .grid import snap_point
from .models import ConnectorRoute, GraphDiagnostics, GraphEdge, GraphVertex, Node, OrthoSegment


Point = tuple[int, int]

MIN_INTERSECTION_LENGTH = 15
MIN_INTERSECTION_SOURCE_COUNT = 2
SPLIT_POINT_MERGE_TOLERANCE = 3


def orthogonalize_paths(
    paths: list[list[Point]],
    orth_axis_tolerance: int,
    spur_min_length: int,
) -> list[list[Point]]:
    ortho_paths: list[list[Point]] = []
    for path in paths:
        if len(path) < 2:
            continue
        current: list[Point] = [snap_point(path[0])]
        for point in path[1:]:
            prev = current[-1]
            point = snap_point(point)
            dx = point[0] - prev[0]
            dy = point[1] - prev[1]
            if abs(dx) <= orth_axis_tolerance and abs(dy) <= orth_axis_tolerance:
                continue
            if abs(dy) <= orth_axis_tolerance:
                next_point = (point[0], prev[1])
                if next_point != current[-1]:
                    current.append(next_point)
            elif abs(dx) <= orth_axis_tolerance:
                next_point = (prev[0], point[1])
                if next_point != current[-1]:
                    current.append(next_point)
            else:
                bend = (point[0], prev[1]) if abs(dx) >= abs(dy) else (prev[0], point[1])
                if bend != current[-1]:
                    current.append(bend)
                if point != current[-1]:
                    current.append(point)
        simplified = [current[0]]
        for point in current[1:]:
            if point != simplified[-1]:
                simplified.append(point)
        if len(simplified) >= 2:
            length = sum(math.dist(simplified[i], simplified[i + 1]) for i in range(len(simplified) - 1))
            if length >= spur_min_length:
                ortho_paths.append(simplified)
    return ortho_paths


def build_ortho_segments(paths: list[list[Point]]) -> list[OrthoSegment]:
    segments: list[OrthoSegment] = []
    for path_index, path in enumerate(paths, start=1):
        for i in range(len(path) - 1):
            x1, y1 = path[i]
            x2, y2 = path[i + 1]
            if x1 == x2 and y1 == y2:
                continue
            orientation = "H" if abs(y1 - y2) <= abs(x1 - x2) else "V"
            if orientation == "H":
                y = int(round((y1 + y2) / 2))
                x1, x2 = sorted([int(x1), int(x2)])
                segments.append(OrthoSegment(id=f"seg_{path_index:03d}_{i:03d}", orientation="H", x1=x1, y1=y, x2=x2, y2=y, component_id=f"comp_{path_index:03d}"))
            else:
                x = int(round((x1 + x2) / 2))
                y1, y2 = sorted([int(y1), int(y2)])
                segments.append(OrthoSegment(id=f"seg_{path_index:03d}_{i:03d}", orientation="V", x1=x, y1=y1, x2=x, y2=y2, component_id=f"comp_{path_index:03d}"))
    return segments


def normalize_ortho_segments(
    segments: list[OrthoSegment],
    axis_snap_tolerance: int,
) -> list[OrthoSegment]:
    normalized: list[OrthoSegment] = []
    for segment in segments:
        if segment.orientation == "H":
            axis = segment.y1
            snapped_axis = int(round(axis / max(axis_snap_tolerance, 1))) * max(axis_snap_tolerance, 1)
            normalized.append(
                OrthoSegment(
                    id=segment.id,
                    orientation="H",
                    x1=min(segment.x1, segment.x2),
                    y1=snapped_axis,
                    x2=max(segment.x1, segment.x2),
                    y2=snapped_axis,
                    component_id=segment.component_id,
                    source_count=segment.source_count,
                    collapsed_from_ids=list(segment.collapsed_from_ids or [segment.id]),
                )
            )
        else:
            axis = segment.x1
            snapped_axis = int(round(axis / max(axis_snap_tolerance, 1))) * max(axis_snap_tolerance, 1)
            normalized.append(
                OrthoSegment(
                    id=segment.id,
                    orientation="V",
                    x1=snapped_axis,
                    y1=min(segment.y1, segment.y2),
                    x2=snapped_axis,
                    y2=max(segment.y1, segment.y2),
                    component_id=segment.component_id,
                    source_count=segment.source_count,
                    collapsed_from_ids=list(segment.collapsed_from_ids or [segment.id]),
                )
            )
    return normalized


def _segment_span(segment: OrthoSegment) -> tuple[int, int]:
    return (segment.x1, segment.x2) if segment.orientation == "H" else (segment.y1, segment.y2)


def _same_axis(first: OrthoSegment, second: OrthoSegment, offset_tolerance: int) -> bool:
    if first.orientation != second.orientation:
        return False
    if first.orientation == "H":
        return abs(first.y1 - second.y1) <= offset_tolerance
    return abs(first.x1 - second.x1) <= offset_tolerance


def _merge_two_collinear(first: OrthoSegment, second: OrthoSegment) -> OrthoSegment:
    if first.orientation == "H":
        xs = [first.x1, first.x2, second.x1, second.x2]
        axis = int(round((first.y1 + second.y1) / 2))
        return OrthoSegment(
            id=first.id,
            orientation="H",
            x1=min(xs),
            y1=axis,
            x2=max(xs),
            y2=axis,
            component_id=first.component_id,
            source_count=first.source_count + second.source_count,
            collapsed_from_ids=(first.collapsed_from_ids or [first.id]) + (second.collapsed_from_ids or [second.id]),
        )
    ys = [first.y1, first.y2, second.y1, second.y2]
    axis = int(round((first.x1 + second.x1) / 2))
    return OrthoSegment(
        id=first.id,
        orientation="V",
        x1=axis,
        y1=min(ys),
        x2=axis,
        y2=max(ys),
        component_id=first.component_id,
        source_count=first.source_count + second.source_count,
        collapsed_from_ids=(first.collapsed_from_ids or [first.id]) + (second.collapsed_from_ids or [second.id]),
    )


def iterative_collinear_merge(
    segments: list[OrthoSegment],
    merge_gap_tolerance: int,
    parallel_offset_tolerance: int,
) -> list[OrthoSegment]:
    merged = list(segments)
    changed = True
    while changed:
        changed = False
        next_segments: list[OrthoSegment] = []
        used = [False] * len(merged)
        for i, segment in enumerate(merged):
            if used[i]:
                continue
            current = segment
            for j in range(i + 1, len(merged)):
                if used[j]:
                    continue
                other = merged[j]
                if not _same_axis(current, other, parallel_offset_tolerance):
                    continue
                a1, a2 = _segment_span(current)
                b1, b2 = _segment_span(other)
                if max(a1, b1) <= min(a2, b2) + merge_gap_tolerance:
                    current = _merge_two_collinear(current, other)
                    used[j] = True
                    changed = True
            next_segments.append(current)
            used[i] = True
        merged = next_segments
    return merged


def collapse_parallel_corridors(
    segments: list[OrthoSegment],
    overlap_ratio_min: float,
    parallel_distance_max: int,
    min_group_size: int,
) -> tuple[list[OrthoSegment], int, list[dict[str, object]]]:
    def overlap_exists(first: OrthoSegment, second: OrthoSegment) -> bool:
        if first.orientation == "H":
            overlap = min(first.x2, second.x2) - max(first.x1, second.x1)
            min_span = max(1, min(first.x2 - first.x1, second.x2 - second.x1))
        else:
            overlap = min(first.y2, second.y2) - max(first.y1, second.y1)
            min_span = max(1, min(first.y2 - first.y1, second.y2 - second.y1))
        return overlap > 0 and (overlap / min_span) >= overlap_ratio_min

    current = list(segments)
    total_collapsed_groups = 0
    debug_groups: list[dict[str, object]] = []
    changed = True
    while changed:
        changed = False
        collapsed: list[OrthoSegment] = []
        used = [False] * len(current)
        for i, segment in enumerate(current):
            if used[i]:
                continue
            group = [segment]
            used[i] = True
            grew = True
            while grew:
                grew = False
                for j, other in enumerate(current):
                    if used[j]:
                        continue
                    if any(
                        item.orientation == other.orientation
                        and abs((item.y1 if item.orientation == "H" else item.x1) - (other.y1 if other.orientation == "H" else other.x1)) <= parallel_distance_max
                        and overlap_exists(item, other)
                        for item in group
                    ):
                        group.append(other)
                        used[j] = True
                        grew = True
            if len(group) >= min_group_size:
                changed = True
                total_collapsed_groups += 1
                debug_groups.append(
                    {
                        "orientation": segment.orientation,
                        "member_segment_ids": [item.id for item in group],
                        "collapsed": True,
                        "overlap_ratio_estimate": round(
                            min(
                                (
                                    max(
                                        0,
                                        min(a.x2 if a.orientation == "H" else a.y2, b.x2 if b.orientation == "H" else b.y2)
                                        - max(a.x1 if a.orientation == "H" else a.y1, b.x1 if b.orientation == "H" else b.y1),
                                    )
                                    / max(
                                        1,
                                        min(
                                            (a.x2 - a.x1) if a.orientation == "H" else (a.y2 - a.y1),
                                            (b.x2 - b.x1) if b.orientation == "H" else (b.y2 - b.y1),
                                        ),
                                    )
                                )
                                for a in group
                                for b in group
                                if a.id != b.id
                            ),
                            3,
                        ) if len(group) > 1 else 1.0,
                        "perpendicular_distance": int(
                            max(
                                abs((item.y1 if item.orientation == "H" else item.x1) - (group[0].y1 if group[0].orientation == "H" else group[0].x1))
                                for item in group
                            )
                        ),
                        "rejection_reason": None,
                    }
                )
                if segment.orientation == "H":
                    x1 = min(item.x1 for item in group)
                    x2 = max(item.x2 for item in group)
                    y = int(round(np.median([item.y1 for item in group])))
                    collapsed.append(
                        OrthoSegment(
                            id=group[0].id,
                            orientation="H",
                            x1=x1,
                            y1=y,
                            x2=x2,
                            y2=y,
                            component_id=group[0].component_id,
                            source_count=sum(item.source_count for item in group),
                            collapsed_from_ids=[sid for item in group for sid in (item.collapsed_from_ids or [item.id])],
                        )
                    )
                else:
                    y1 = min(item.y1 for item in group)
                    y2 = max(item.y2 for item in group)
                    x = int(round(np.median([item.x1 for item in group])))
                    collapsed.append(
                        OrthoSegment(
                            id=group[0].id,
                            orientation="V",
                            x1=x,
                            y1=y1,
                            x2=x,
                            y2=y2,
                            component_id=group[0].component_id,
                            source_count=sum(item.source_count for item in group),
                            collapsed_from_ids=[sid for item in group for sid in (item.collapsed_from_ids or [item.id])],
                        )
                    )
            else:
                if len(group) > 1:
                    debug_groups.append(
                        {
                            "orientation": segment.orientation,
                            "member_segment_ids": [item.id for item in group],
                            "collapsed": False,
                            "overlap_ratio_estimate": 0.0,
                            "perpendicular_distance": int(
                                max(
                                    abs((item.y1 if item.orientation == "H" else item.x1) - (group[0].y1 if group[0].orientation == "H" else group[0].x1))
                                    for item in group
                                )
                            ),
                            "rejection_reason": "group_size_below_threshold",
                        }
                    )
                collapsed.extend(group)
        current = collapsed
    return current, total_collapsed_groups, debug_groups


def filter_dominant_segments(
    segments: list[OrthoSegment],
    parallel_offset_tolerance: int,
) -> list[OrthoSegment]:
    kept: list[OrthoSegment] = []
    for segment in sorted(segments, key=_segment_length, reverse=True):
        dominated = False
        for existing in kept:
            if segment.orientation != existing.orientation:
                continue
            if segment.orientation == "H":
                if abs(segment.y1 - existing.y1) <= parallel_offset_tolerance and existing.x1 <= segment.x1 and segment.x2 <= existing.x2:
                    dominated = True
                    break
            else:
                if abs(segment.x1 - existing.x1) <= parallel_offset_tolerance and existing.y1 <= segment.y1 and segment.y2 <= existing.y2:
                    dominated = True
                    break
        if not dominated:
            kept.append(segment)
    return kept


def _segment_length(segment: OrthoSegment) -> float:
    return float(abs(segment.x2 - segment.x1) + abs(segment.y2 - segment.y1))


def _point_on_segment(point: Point, segment: OrthoSegment) -> bool:
    x, y = point
    if segment.orientation == "H":
        return y == segment.y1 and segment.x1 <= x <= segment.x2
    return x == segment.x1 and segment.y1 <= y <= segment.y2


def _graph_points_from_segments(segments: list[OrthoSegment]) -> dict[Point, set[int]]:
    point_map: dict[Point, set[int]] = defaultdict(set)
    for index, segment in enumerate(segments):
        point_map[(segment.x1, segment.y1)].add(index)
        point_map[(segment.x2, segment.y2)].add(index)
        for other_index in range(index + 1, len(segments)):
            other = segments[other_index]
            if segment.orientation == other.orientation:
                continue
            h = segment if segment.orientation == "H" else other
            v = other if segment.orientation == "V" else segment
            if h.x1 <= v.x1 <= h.x2 and v.y1 <= h.y1 <= v.y2:
                point_map[(v.x1, h.y1)].update({index, other_index})
    return point_map


def prune_spurs(
    segments: list[OrthoSegment],
    gate_points: list[Point],
    spur_prune_length: int,
) -> tuple[list[OrthoSegment], int]:
    point_map = _graph_points_from_segments(segments)
    protected_points = set(gate_points)
    kept: list[OrthoSegment] = []
    pruned = 0
    for index, segment in enumerate(segments):
        degree_start = len(point_map[(segment.x1, segment.y1)])
        degree_end = len(point_map[(segment.x2, segment.y2)])
        if (
            _segment_length(segment) <= spur_prune_length
            and (degree_start == 1 or degree_end == 1)
            and (segment.x1, segment.y1) not in protected_points
            and (segment.x2, segment.y2) not in protected_points
        ):
            pruned += 1
            continue
        kept.append(segment)
    return kept, pruned


def segments_to_component_graph(segments: list[OrthoSegment]) -> dict[int, set[int]]:
    graph: dict[int, set[int]] = {i: set() for i in range(len(segments))}
    point_map = _graph_points_from_segments(segments)
    for indexes in point_map.values():
        index_list = list(indexes)
        for i in range(len(index_list)):
            for j in range(i + 1, len(index_list)):
                graph[index_list[i]].add(index_list[j])
                graph[index_list[j]].add(index_list[i])
    return graph


def filter_gate_relevant_segments(
    segments: list[OrthoSegment],
    gate_points: list[Point],
    component_gate_distance_max: int,
) -> tuple[list[OrthoSegment], int]:
    graph = segments_to_component_graph(segments)
    seen: set[int] = set()
    components: list[list[int]] = []
    component_points: list[list[Point]] = []
    for start in range(len(segments)):
        if start in seen:
            continue
        queue = deque([start])
        component: list[int] = []
        seen.add(start)
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in graph[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        components.append(component)
        pts: list[Point] = []
        for index in component:
            seg = segments[index]
            pts.extend([(seg.x1, seg.y1), (seg.x2, seg.y2)])
        component_points.append(pts)

    component_graph: dict[int, set[int]] = {i: set() for i in range(len(components))}
    for i in range(len(components)):
        box_i = (
            min(p[0] for p in component_points[i]),
            min(p[1] for p in component_points[i]),
            max(p[0] for p in component_points[i]),
            max(p[1] for p in component_points[i]),
        )
        for j in range(i + 1, len(components)):
            box_j = (
                min(p[0] for p in component_points[j]),
                min(p[1] for p in component_points[j]),
                max(p[0] for p in component_points[j]),
                max(p[1] for p in component_points[j]),
            )
            dx = max(0, max(box_i[0], box_j[0]) - min(box_i[2], box_j[2]))
            dy = max(0, max(box_i[1], box_j[1]) - min(box_i[3], box_j[3]))
            if max(dx, dy) <= component_gate_distance_max:
                component_graph[i].add(j)
                component_graph[j].add(i)

    seed_components = set()
    for index, pts in enumerate(component_points):
        min_distance = min(math.dist(point, gate) for point in pts for gate in gate_points) if gate_points else float("inf")
        if min_distance <= component_gate_distance_max:
            seed_components.add(index)

    kept_component_indexes = set(seed_components)
    queue = deque(seed_components)
    while queue:
        current = queue.popleft()
        for neighbor in component_graph[current]:
            if neighbor not in kept_component_indexes:
                kept_component_indexes.add(neighbor)
                queue.append(neighbor)

    kept_indexes: set[int] = set()
    for component_index in kept_component_indexes:
        kept_indexes.update(components[component_index])
    kept = [segment for i, segment in enumerate(segments) if i in kept_indexes]
    return kept, len(kept_component_indexes)


def filter_graph_to_gate_reachable(
    vertices: list[GraphVertex],
    edges: list[GraphEdge],
    seed_vertex_ids: list[str] | None = None,
) -> tuple[list[GraphVertex], list[GraphEdge], int]:
    adjacency: defaultdict[str, set[str]] = defaultdict(set)
    for edge in edges:
        adjacency[edge.v_start].add(edge.v_end)
        adjacency[edge.v_end].add(edge.v_start)

    gate_vertex_ids = set(seed_vertex_ids or [vertex.id for vertex in vertices if vertex.kind == "gate_attach"])
    reachable = set(gate_vertex_ids)
    queue = deque(gate_vertex_ids)
    while queue:
        current = queue.popleft()
        for neighbor in adjacency[current]:
            if neighbor not in reachable:
                reachable.add(neighbor)
                queue.append(neighbor)

    kept_vertices = [vertex for vertex in vertices if vertex.id in reachable]
    kept_edges = [edge for edge in edges if edge.v_start in reachable and edge.v_end in reachable]
    return kept_vertices, kept_edges, len(gate_vertex_ids)


def _segment_intersection(first: OrthoSegment, second: OrthoSegment) -> Point | None:
    if first.orientation == second.orientation:
        return None
    h = first if first.orientation == "H" else second
    v = second if first.orientation == "H" else first
    if h.x1 <= v.x1 <= h.x2 and v.y1 <= h.y1 <= v.y2:
        return (v.x1, h.y1)
    return None


def _connected_intersection(point: Point, connector_space: np.ndarray, continuity_radius: int) -> bool:
    x, y = point
    h, w = connector_space.shape[:2]
    x1 = max(0, x - continuity_radius)
    y1 = max(0, y - continuity_radius)
    x2 = min(w, x + continuity_radius + 1)
    y2 = min(h, y + continuity_radius + 1)
    roi = connector_space[y1:y2, x1:x2]
    if int(cv2.countNonZero(roi)) < max(3, continuity_radius * 2):
        return False

    horizontal_window = connector_space[y:y + 1, x1:x2]
    vertical_window = connector_space[y1:y2, x:x + 1]
    if horizontal_window.size == 0 or vertical_window.size == 0:
        return False

    horizontal_support = int(cv2.countNonZero(horizontal_window)) / float(horizontal_window.size)
    vertical_support = int(cv2.countNonZero(vertical_window)) / float(vertical_window.size)
    if horizontal_support < 0.6 or vertical_support < 0.6:
        return False

    left_roi = connector_space[y:y + 1, x1:x]
    right_roi = connector_space[y:y + 1, x + 1:x2]
    up_roi = connector_space[y1:y, x:x + 1]
    down_roi = connector_space[y + 1:y2, x:x + 1]
    directional_supports = []
    for sample in (left_roi, right_roi, up_roi, down_roi):
        if sample.size == 0:
            return False
        directional_supports.append(int(cv2.countNonZero(sample)) / float(sample.size))
    return all(support >= 0.5 for support in directional_supports)


def _next_edge_id(edges: list[GraphEdge]) -> str:
    max_index = 0
    for edge in edges:
        try:
            max_index = max(max_index, int(edge.id.split("_", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"e_{max_index + 1:03d}"


def _edge_debug_with_defaults(debug: dict[str, object]) -> dict[str, object]:
    normalized = dict(debug)
    normalized.setdefault("source_segment_id", None)
    normalized["source_segment_stage"] = "collapsed_segments"
    normalized.setdefault("split_from_intersection", False)
    return normalized


def _intersection_endpoint_supported(
    point: Point,
    first: OrthoSegment,
    second: OrthoSegment,
    endpoint_tolerance: int,
) -> bool:
    first_endpoints = [(first.x1, first.y1), (first.x2, first.y2)]
    second_endpoints = [(second.x1, second.y1), (second.x2, second.y2)]
    first_near = min(math.dist(point, endpoint) for endpoint in first_endpoints) <= endpoint_tolerance
    second_near = min(math.dist(point, endpoint) for endpoint in second_endpoints) <= endpoint_tolerance
    strong_first = _segment_length(first) >= MIN_INTERSECTION_LENGTH or first.source_count >= MIN_INTERSECTION_SOURCE_COUNT
    strong_second = _segment_length(second) >= MIN_INTERSECTION_LENGTH or second.source_count >= MIN_INTERSECTION_SOURCE_COUNT
    return ((first_near and strong_first) or (second_near and strong_second))


def _segment_participates_in_intersections(segment: OrthoSegment) -> bool:
    return _segment_length(segment) >= MIN_INTERSECTION_LENGTH or segment.source_count >= MIN_INTERSECTION_SOURCE_COUNT


def _pair_participates_in_intersections(first: OrthoSegment, second: OrthoSegment) -> bool:
    shorter_length = min(_segment_length(first), _segment_length(second))
    if first.source_count <= 1 and second.source_count <= 1 and shorter_length < 25:
        return False
    return True


def _merge_close_split_points(segment: OrthoSegment, points: list[Point]) -> list[Point]:
    ordered = sorted(
        {point for point in points if _point_on_segment(point, segment)},
        key=lambda point: _point_sort_key_for_segment(point, segment),
    )
    if not ordered:
        return []

    merged = [ordered[0]]
    for point in ordered[1:]:
        if _point_sort_key_for_segment(point, segment) - _point_sort_key_for_segment(merged[-1], segment) <= SPLIT_POINT_MERGE_TOLERANCE:
            continue
        merged.append(point)
    return merged


def _point_sort_key_for_segment(point: Point, segment: OrthoSegment) -> int:
    return point[0] if segment.orientation == "H" else point[1]


def _split_segment_at_points(
    segment: OrthoSegment,
    split_points: list[Point],
) -> list[OrthoSegment]:
    unique_points = set(_merge_close_split_points(segment, split_points))
    unique_points.add((segment.x1, segment.y1))
    unique_points.add((segment.x2, segment.y2))
    ordered_points = sorted(unique_points, key=lambda point: _point_sort_key_for_segment(point, segment))

    split_segments: list[OrthoSegment] = []
    for index in range(len(ordered_points) - 1):
        start = ordered_points[index]
        end = ordered_points[index + 1]
        if start == end:
            continue
        child = OrthoSegment(
            id=f"{segment.id}__split_{index:03d}",
            orientation=segment.orientation,
            x1=start[0],
            y1=start[1],
            x2=end[0],
            y2=end[1],
            component_id=segment.component_id,
            source_count=segment.source_count,
            collapsed_from_ids=list(segment.collapsed_from_ids or [segment.id]),
        )
        if _segment_length(child) <= 0:
            continue
        split_segments.append(child)
    return split_segments


def build_graph(
    segments: list[OrthoSegment],
    connector_space: np.ndarray,
    continuity_radius: int,
    endpoint_intersection_tolerance: int,
) -> tuple[list[GraphVertex], list[GraphEdge], list[dict[str, object]], dict[str, int]]:
    accepted_points_by_segment: defaultdict[str, set[Point]] = defaultdict(set)
    accepted_intersections: list[dict[str, object]] = []
    intersections_rejected_by_reason: defaultdict[str, int] = defaultdict(int)
    intersections_detected_raw = 0
    intersections_accepted = 0
    segments_blocked_from_splitting = 0
    blocked_segment_ids: set[str] = set()

    for index, first in enumerate(segments):
        if not _segment_participates_in_intersections(first):
            blocked_segment_ids.add(first.id)
            continue
        for second in segments[index + 1 :]:
            if not _segment_participates_in_intersections(second):
                blocked_segment_ids.add(second.id)
                continue
            if not _pair_participates_in_intersections(first, second):
                intersections_rejected_by_reason["weak_segment_pair"] += 1
                continue
            point = _segment_intersection(first, second)
            if point is None:
                continue
            intersections_detected_raw += 1
            connected = _connected_intersection(point, connector_space, continuity_radius)
            endpoint_supported = _intersection_endpoint_supported(
                point,
                first,
                second,
                endpoint_intersection_tolerance,
            )
            if not connected and not endpoint_supported:
                if not _connected_intersection(point, connector_space, continuity_radius):
                    intersections_rejected_by_reason["weak_axis_support"] += 1
                else:
                    intersections_rejected_by_reason["endpoint_proximity_rejected"] += 1
                continue
            intersections_accepted += 1
            accepted_points_by_segment[first.id].add(point)
            accepted_points_by_segment[second.id].add(point)
            accepted_intersections.append(
                {
                    "point": point,
                    "first_segment_id": first.id,
                    "second_segment_id": second.id,
                    "connected_intersection": connected,
                    "endpoint_supported": endpoint_supported,
                    "accepted": True,
                }
            )

    split_segments: list[OrthoSegment] = []
    segments_split = 0
    split_edges_created = 0
    max_splits_per_segment = 0
    vertex_points: set[Point] = set()
    for segment in segments:
        segment_split_points = list(accepted_points_by_segment.get(segment.id, set()))
        parts = _split_segment_at_points(segment, segment_split_points)
        if len(parts) > 1:
            segments_split += 1
        max_splits_per_segment = max(max_splits_per_segment, max(0, len(parts) - 1))
        split_edges_created += len(parts)
        split_segments.extend(parts)
        vertex_points.add((segment.x1, segment.y1))
        vertex_points.add((segment.x2, segment.y2))
        vertex_points.update(segment_split_points)

    sorted_points = sorted(vertex_points, key=lambda p: (p[1], p[0]))
    vertices: list[GraphVertex] = []
    vertex_ids: dict[Point, str] = {}
    for index, point in enumerate(sorted_points, start=1):
        vertex = GraphVertex(id=f"v_{index:03d}", kind="endpoint", x=point[0], y=point[1], degree=0)
        vertices.append(vertex)
        vertex_ids[point] = vertex.id

    edges: list[GraphEdge] = []
    adjacency: defaultdict[str, set[str]] = defaultdict(set)
    for segment in split_segments:
        start = vertex_ids[(segment.x1, segment.y1)]
        end = vertex_ids[(segment.x2, segment.y2)]
        if start == end:
            continue
        edge = GraphEdge(
            id=_next_edge_id(edges),
            v_start=start,
            v_end=end,
            orientation=segment.orientation,
            length=round(_segment_length(segment), 2),
            debug=_edge_debug_with_defaults({
                "source_segment_id": segment.id.split("__split_")[0],
                "split_from_intersection": bool(accepted_points_by_segment.get(segment.id.split("__split_")[0])),
                "split_index": int(segment.id.rsplit("__split_", 1)[1]) if "__split_" in segment.id else 0,
            }),
        )
        edges.append(edge)
        adjacency[start].add(end)
        adjacency[end].add(start)

    junction_vertices_created = 0
    for vertex in vertices:
        vertex.degree = len(adjacency[vertex.id])
        if vertex.degree >= 3:
            vertex.kind = "junction"
            junction_vertices_created += 1
        elif vertex.degree == 2:
            vertex.kind = "bend"
        else:
            vertex.kind = "endpoint"

    metrics = {
        "intersections_candidates_raw": intersections_detected_raw,
        "intersections_detected_raw": intersections_detected_raw,
        "intersections_accepted": intersections_accepted,
        "intersections_rejected_by_reason": dict(intersections_rejected_by_reason),
        "segments_split": segments_split,
        "split_edges_created": split_edges_created,
        "junction_vertices_created": junction_vertices_created,
        "max_splits_per_segment": max_splits_per_segment,
        "segments_blocked_from_splitting": len(blocked_segment_ids),
    }
    return vertices, edges, accepted_intersections, metrics


def reduce_degree2_vertices(vertices: list[GraphVertex], edges: list[GraphEdge]) -> tuple[list[GraphVertex], list[GraphEdge], int, int]:
    vertex_lookup = {vertex.id: vertex for vertex in vertices}
    adjacency: defaultdict[str, list[GraphEdge]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.v_start].append(edge)
        adjacency[edge.v_end].append(edge)

    removed = 0
    candidate_count = 0
    changed = True
    current_edges = list(edges)
    current_vertices = list(vertices)
    while changed:
        changed = False
        adjacency = defaultdict(list)
        for edge in current_edges:
            adjacency[edge.v_start].append(edge)
            adjacency[edge.v_end].append(edge)
        for vertex in list(current_vertices):
            if vertex.kind in {"junction", "crossing", "gate_attach"}:
                continue
            incident = adjacency.get(vertex.id, [])
            if len(incident) != 2:
                continue
            first, second = incident
            if first.orientation != second.orientation:
                continue
            candidate_count += 1
            other_a = first.v_end if first.v_start == vertex.id else first.v_start
            other_b = second.v_end if second.v_start == vertex.id else second.v_start
            if other_a == other_b:
                continue
            current_edges = [edge for edge in current_edges if edge.id not in {first.id, second.id}]
            current_edges.append(
                GraphEdge(
                    id=_next_edge_id(current_edges),
                    v_start=other_a,
                    v_end=other_b,
                    orientation=first.orientation,
                    length=round(first.length + second.length, 2),
                    debug=_edge_debug_with_defaults({
                        "source_segment_id": first.debug.get("source_segment_id"),
                        "split_from_intersection": bool(first.debug.get("split_from_intersection") or second.debug.get("split_from_intersection")),
                        "merged_from_edges": [first.id, second.id],
                    }),
                )
            )
            current_vertices = [item for item in current_vertices if item.id != vertex.id]
            removed += 1
            changed = True
            break
    degree_counts: defaultdict[str, int] = defaultdict(int)
    for edge in current_edges:
        degree_counts[edge.v_start] += 1
        degree_counts[edge.v_end] += 1
    for vertex in current_vertices:
        vertex.degree = degree_counts[vertex.id]
    return current_vertices, current_edges, removed, candidate_count


def _reclassify_vertices(vertices: list[GraphVertex], edges: list[GraphEdge]) -> list[GraphVertex]:
    degree_counts: defaultdict[str, int] = defaultdict(int)
    for edge in edges:
        degree_counts[edge.v_start] += 1
        degree_counts[edge.v_end] += 1
    for vertex in vertices:
        vertex.degree = degree_counts[vertex.id]
        if vertex.degree >= 3:
            vertex.kind = "junction"
        elif vertex.degree == 2:
            vertex.kind = "bend"
        else:
            vertex.kind = "endpoint"
    return vertices


def summarize_final_graph(vertices: list[GraphVertex], edges: list[GraphEdge]) -> dict[str, int]:
    def degree_of(vertex: GraphVertex | dict[str, object]) -> int:
        if isinstance(vertex, dict):
            return int(vertex.get("degree", 0))
        return int(vertex.degree)

    return {
        "final_graph_vertices": len(vertices),
        "final_graph_edges": len(edges),
        "final_graph_junction_vertices": sum(1 for vertex in vertices if degree_of(vertex) >= 3),
        "final_graph_bend_vertices": sum(1 for vertex in vertices if degree_of(vertex) == 2),
        "final_graph_endpoint_vertices": sum(1 for vertex in vertices if degree_of(vertex) == 1),
    }


def prune_nonprotected_leaves(
    vertices: list[GraphVertex],
    edges: list[GraphEdge],
    protected_vertex_ids: set[str],
) -> tuple[list[GraphVertex], list[GraphEdge], int]:
    current_vertices = list(vertices)
    current_edges = list(edges)
    removed = 0

    changed = True
    while changed:
        changed = False
        adjacency: defaultdict[str, list[GraphEdge]] = defaultdict(list)
        for edge in current_edges:
            adjacency[edge.v_start].append(edge)
            adjacency[edge.v_end].append(edge)

        removable = [
            vertex.id
            for vertex in current_vertices
            if vertex.id not in protected_vertex_ids and len(adjacency.get(vertex.id, [])) <= 1
        ]
        if not removable:
            break
        removable_ids = set(removable)
        removed += len(removable_ids)
        current_vertices = [vertex for vertex in current_vertices if vertex.id not in removable_ids]
        current_edges = [
            edge
            for edge in current_edges
            if edge.v_start not in removable_ids and edge.v_end not in removable_ids
        ]
        changed = True

    return _reclassify_vertices(current_vertices, current_edges), current_edges, removed


def _manhattan(point_a: Point, point_b: Point) -> int:
    return abs(point_a[0] - point_b[0]) + abs(point_a[1] - point_b[1])


def _project_point_to_segment(point: Point, segment: OrthoSegment) -> Point:
    if segment.orientation == "H":
        return (min(max(point[0], segment.x1), segment.x2), segment.y1)
    return (segment.x1, min(max(point[1], segment.y1), segment.y2))


def _segment_axis_distance(point: Point, segment: OrthoSegment) -> int:
    projection = _project_point_to_segment(point, segment)
    return _manhattan(point, projection)


def _orthogonal_gate_elbow(gate_point: Point, next_point: Point, side: str) -> Point:
    if side in {"left", "right"}:
        return (next_point[0], gate_point[1])
    return (gate_point[0], next_point[1])


def _segment_orientation_and_length(first: Point, second: Point) -> tuple[str | None, int]:
    if first[0] == second[0]:
        return "V", abs(second[1] - first[1])
    if first[1] == second[1]:
        return "H", abs(second[0] - first[0])
    return None, int(round(math.dist(first, second)))


def _remove_duplicate_route_points(points: list[Point]) -> list[Point]:
    cleaned: list[Point] = []
    for point in points:
        snapped = snap_point(point)
        if not cleaned or snapped != cleaned[-1]:
            cleaned.append(snapped)
    return cleaned


def _remove_collinear_route_points(points: list[Point]) -> list[Point]:
    if len(points) < 3:
        return points
    cleaned = [points[0]]
    for point in points[1:]:
        cleaned.append(point)
        while len(cleaned) >= 3:
            first, second, third = cleaned[-3:]
            if (first[0] == second[0] == third[0]) or (first[1] == second[1] == third[1]):
                cleaned.pop(-2)
            else:
                break
    return cleaned


def _normalize_same_side_route_axis(
    points: list[Point],
    src_side: str,
    dst_side: str,
    axis_snap_tolerance: int,
    micro_bend_threshold: int,
) -> tuple[list[Point], bool]:
    if len(points) < 3 or src_side != dst_side:
        return points, False

    adjusted = list(points)
    changed = False
    if src_side in {"top", "bottom"}:
        target_y = int(round((points[0][1] + points[-1][1]) / 2))
        if abs(points[0][1] - points[-1][1]) > axis_snap_tolerance:
            return points, False
        for index in range(1, len(adjusted) - 1):
            point = adjusted[index]
            if abs(point[1] - target_y) <= micro_bend_threshold:
                snapped = (point[0], target_y)
                if snapped != point:
                    adjusted[index] = snapped
                    changed = True
    elif src_side in {"left", "right"}:
        target_x = int(round((points[0][0] + points[-1][0]) / 2))
        if abs(points[0][0] - points[-1][0]) > axis_snap_tolerance:
            return points, False
        for index in range(1, len(adjusted) - 1):
            point = adjusted[index]
            if abs(point[0] - target_x) <= micro_bend_threshold:
                snapped = (target_x, point[1])
                if snapped != point:
                    adjusted[index] = snapped
                    changed = True
    return adjusted, changed


def _collapse_micro_rectangles(points: list[Point], micro_bend_threshold: int) -> tuple[list[Point], int]:
    if len(points) < 4:
        return points, 0
    working = list(points)
    removed = 0
    changed = True
    while changed and len(working) >= 4:
        changed = False
        for index in range(len(working) - 3):
            p0, p1, p2, p3 = working[index : index + 4]
            o01, l01 = _segment_orientation_and_length(p0, p1)
            o12, l12 = _segment_orientation_and_length(p1, p2)
            o23, l23 = _segment_orientation_and_length(p2, p3)
            if None in {o01, o12, o23}:
                continue
            if o01 != o23 or o01 == o12:
                continue
            if max(l01, l23) > micro_bend_threshold:
                continue
            if o01 == "H" and p0[1] == p3[1]:
                working = working[: index + 1] + [p3] + working[index + 4 :]
                removed += 2
                changed = True
                break
            if o01 == "V" and p0[0] == p3[0]:
                working = working[: index + 1] + [p3] + working[index + 4 :]
                removed += 2
                changed = True
                break
    return working, removed


def cleanup_route_shape(
    points: list[Point],
    src_side: str,
    dst_side: str,
    micro_bend_threshold: int,
    axis_snap_tolerance: int,
) -> tuple[list[Point], dict[str, object]]:
    cleaned = _remove_duplicate_route_points(points)
    cleaned = _remove_collinear_route_points(cleaned)
    cleaned = _remove_duplicate_route_points(cleaned)
    cleaned = _remove_collinear_route_points(cleaned)
    cleaned, micro_removed = _collapse_micro_rectangles(cleaned, micro_bend_threshold=micro_bend_threshold)
    cleaned = _remove_duplicate_route_points(cleaned)
    cleaned = _remove_collinear_route_points(cleaned)
    if len(cleaned) < 2:
        cleaned = _remove_duplicate_route_points(points)
    return cleaned, {
        "point_count_before_cleanup": len(points),
        "point_count_after_cleanup": len(cleaned),
        "micro_bends_removed": micro_removed,
        "endpoint_normalized": False,
        "axis_normalized": False,
    }


def absorb_gate_stubs_and_cleanup(
    nodes: list[Node],
    segments: list[OrthoSegment],
    vertices: list[GraphVertex],
    edges: list[GraphEdge],
    attach_tolerance: int,
    micro_bend_threshold: int,
) -> tuple[list[GraphVertex], list[GraphEdge], list[dict[str, object]], dict[str, int]]:
    vertex_lookup = {vertex.id: vertex for vertex in vertices}
    segment_by_id = {segment.id: segment for segment in segments}
    attachments: list[dict[str, object]] = []
    gate_stubs_absorbed = 0
    corridor_contacts_snapped = 0

    for node in nodes:
        for side, gate_point in node.gates.items():
            best_vertex = None
            best_vertex_distance = float("inf")
            for vertex in vertices:
                distance = math.dist(gate_point, (vertex.x, vertex.y))
                if distance < best_vertex_distance:
                    best_vertex_distance = distance
                    best_vertex = vertex

            best_edge = None
            best_edge_distance = float("inf")
            best_projection = None
            for edge in edges:
                segment_id = edge.debug.get("source_segment_id")
                segment = segment_by_id.get(segment_id)
                if segment is None:
                    continue
                distance = _segment_axis_distance(gate_point, segment)
                if distance < best_edge_distance:
                    best_edge_distance = distance
                    best_edge = edge
                    best_projection = _project_point_to_segment(gate_point, segment)

            if best_vertex is not None and best_vertex_distance <= attach_tolerance:
                attachments.append(
                    {
                        "node_id": node.id,
                        "side": side,
                        "gate_point": gate_point,
                        "vertex_id": best_vertex.id,
                        "graph_vertex_id": best_vertex.id,
                        "distance": round(best_vertex_distance, 2),
                        "stub_absorbed": False,
                        "snapped_to_corridor": False,
                    }
                )
                continue

            if best_edge is not None and best_edge_distance <= attach_tolerance and best_projection is not None:
                start_vertex = vertex_lookup.get(best_edge.v_start)
                end_vertex = vertex_lookup.get(best_edge.v_end)
                if start_vertex is None or end_vertex is None:
                    continue
                preferred_vertex = start_vertex
                preferred_distance = _manhattan(best_projection, (start_vertex.x, start_vertex.y))
                end_distance = _manhattan(best_projection, (end_vertex.x, end_vertex.y))
                if end_distance < preferred_distance:
                    preferred_vertex = end_vertex
                attachments.append(
                    {
                        "node_id": node.id,
                        "side": side,
                        "gate_point": gate_point,
                        "vertex_id": preferred_vertex.id,
                        "graph_vertex_id": preferred_vertex.id,
                        "distance": round(best_edge_distance, 2),
                        "stub_absorbed": True,
                        "snapped_to_corridor": True,
                        "projected_point": best_projection,
                        "edge_id": best_edge.id,
                    }
                )
                gate_stubs_absorbed += 1
                corridor_contacts_snapped += 1

    reduced_vertices, reduced_edges, degree2_removed, _ = reduce_degree2_vertices(vertices, edges)

    vertex_lookup = {vertex.id: vertex for vertex in reduced_vertices}
    edge_lookup: defaultdict[str, list[GraphEdge]] = defaultdict(list)
    for edge in reduced_edges:
        edge_lookup[edge.v_start].append(edge)
        edge_lookup[edge.v_end].append(edge)

    micro_bends_removed = 0
    changed = True
    while changed:
        changed = False
        for vertex in list(reduced_vertices):
            if vertex.kind not in {"bend", "endpoint"}:
                continue
            incident = edge_lookup.get(vertex.id, [])
            if len(incident) != 2:
                continue
            first, second = incident
            other_a = first.v_end if first.v_start == vertex.id else first.v_start
            other_b = second.v_end if second.v_start == vertex.id else second.v_start
            if other_a == other_b:
                continue
            if first.orientation == second.orientation:
                continue
            point_a = (vertex_lookup[other_a].x, vertex_lookup[other_a].y)
            point_b = (vertex_lookup[other_b].x, vertex_lookup[other_b].y)
            if _manhattan((vertex.x, vertex.y), point_a) > micro_bend_threshold and _manhattan((vertex.x, vertex.y), point_b) > micro_bend_threshold:
                continue
            new_orientation = "H" if abs(point_a[1] - point_b[1]) <= abs(point_a[0] - point_b[0]) else "V"
            reduced_edges = [edge for edge in reduced_edges if edge.id not in {first.id, second.id}]
            reduced_edges.append(
                GraphEdge(
                    id=_next_edge_id(reduced_edges),
                    v_start=other_a,
                    v_end=other_b,
                    orientation=new_orientation,
                    length=round(math.dist(point_a, point_b), 2),
                    debug=_edge_debug_with_defaults({
                        "source_segment_id": first.debug.get("source_segment_id"),
                        "split_from_intersection": bool(first.debug.get("split_from_intersection") or second.debug.get("split_from_intersection")),
                        "merged_from_edges": [first.id, second.id],
                        "micro_bend_removed": True,
                    }),
                )
            )
            reduced_vertices = [item for item in reduced_vertices if item.id != vertex.id]
            vertex_lookup.pop(vertex.id, None)
            micro_bends_removed += 1
            changed = True
            edge_lookup = defaultdict(list)
            for edge in reduced_edges:
                edge_lookup[edge.v_start].append(edge)
                edge_lookup[edge.v_end].append(edge)
            break

    degree_counts: defaultdict[str, int] = defaultdict(int)
    for edge in reduced_edges:
        degree_counts[edge.v_start] += 1
        degree_counts[edge.v_end] += 1
    for vertex in reduced_vertices:
        vertex.degree = degree_counts[vertex.id]
        if vertex.degree >= 3:
            vertex.kind = "junction"
        elif vertex.degree == 2:
            vertex.kind = "bend"
        else:
            vertex.kind = "endpoint"

    attachment_vertex_ids = {attachment["vertex_id"] for attachment in attachments}
    reduced_vertices, reduced_edges, pruned_leaf_vertices = prune_nonprotected_leaves(
        reduced_vertices,
        reduced_edges,
        attachment_vertex_ids,
    )
    degree2_endpoints_reclassified = sum(
        1
        for attachment in attachments
        if attachment.get("stub_absorbed") or (
            attachment["vertex_id"] in attachment_vertex_ids
            and any(vertex.id == attachment["vertex_id"] and vertex.degree == 2 and vertex.kind == "bend" for vertex in reduced_vertices)
        )
    )

    return reduced_vertices, reduced_edges, attachments, {
        "degree2_endpoints_reclassified": degree2_endpoints_reclassified,
        "gate_stubs_absorbed": gate_stubs_absorbed,
        "micro_bends_removed": micro_bends_removed,
        "corridor_contacts_snapped": corridor_contacts_snapped,
        "degree2_vertices_removed_post_attach": degree2_removed,
        "leaf_vertices_pruned_post_attach": pruned_leaf_vertices,
    }


def attach_gates_to_graph(
    nodes: list[Node],
    segments: list[OrthoSegment],
    vertices: list[GraphVertex],
    edges: list[GraphEdge],
    attach_tolerance: int,
    micro_bend_threshold: int,
) -> tuple[list[GraphVertex], list[GraphEdge], list[dict[str, object]], dict[str, int]]:
    return absorb_gate_stubs_and_cleanup(
        nodes=nodes,
        segments=segments,
        vertices=vertices,
        edges=edges,
        attach_tolerance=attach_tolerance,
        micro_bend_threshold=micro_bend_threshold,
    )


def filter_graph_to_routes(
    vertices: list[GraphVertex],
    edges: list[GraphEdge],
    routes: list[ConnectorRoute],
) -> tuple[list[GraphVertex], list[GraphEdge]]:
    used_vertex_ids: set[str] = set()
    used_edge_pairs: set[tuple[str, str]] = set()
    for route in routes:
        used_vertex_ids.update(route.vertex_path)
        for index in range(len(route.vertex_path) - 1):
            first = route.vertex_path[index]
            second = route.vertex_path[index + 1]
            used_edge_pairs.add(tuple(sorted((first, second))))

    kept_vertices = [vertex for vertex in vertices if vertex.id in used_vertex_ids]
    kept_edges = [
        edge
        for edge in edges
        if tuple(sorted((edge.v_start, edge.v_end))) in used_edge_pairs
    ]
    return _reclassify_vertices(kept_vertices, kept_edges), kept_edges


def _keep_route_candidate(route: ConnectorRoute, support_count: int) -> bool:
    attachment_distance_sum = float(route.debug.get("attachment_distance_sum", float("inf")))
    simplified_edge_count = int(route.debug.get("simplified_edge_count", 0))
    if support_count < 5 and attachment_distance_sum > 50.0:
        return False
    if simplified_edge_count > 6 and support_count < 8:
        return False
    return support_count >= 3 or attachment_distance_sum <= 20.0


def route_recovered_paths_via_graph(
    ortho_paths: list[list[Point]],
    attachments: list[dict[str, object]],
    vertices: list[GraphVertex],
    edges: list[GraphEdge],
    endpoint_tolerance: int,
    micro_bend_threshold: int = 10,
    axis_snap_tolerance: int = 3,
) -> list[ConnectorRoute]:
    vertex_lookup = {vertex.id: (vertex.x, vertex.y) for vertex in vertices}
    adjacency: defaultdict[str, list[str]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.v_start].append(edge.v_end)
        adjacency[edge.v_end].append(edge.v_start)

    def shortest_path(start_id: str, end_id: str) -> list[str] | None:
        queue = deque([(start_id, [start_id])])
        seen = {start_id}
        while queue:
            current, vertex_path = queue.popleft()
            if current == end_id:
                return vertex_path
            for neighbor in adjacency[current]:
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append((neighbor, vertex_path + [neighbor]))
        return None

    def best_attachment_pair(path: list[Point]) -> tuple[dict[str, object], dict[str, object], float, float] | None:
        if len(path) < 2:
            return None
        start_point = path[0]
        end_point = path[-1]
        start_candidates = sorted(
            ((math.dist(start_point, attachment["gate_point"]), attachment) for attachment in attachments),
            key=lambda item: item[0],
        )[:6]
        end_candidates = sorted(
            ((math.dist(end_point, attachment["gate_point"]), attachment) for attachment in attachments),
            key=lambda item: item[0],
        )[:6]
        best_pair: tuple[dict[str, object], dict[str, object], float, float] | None = None
        best_score = float("inf")
        for start_distance, start_attachment in start_candidates:
            for end_distance, end_attachment in end_candidates:
                if start_attachment["node_id"] == end_attachment["node_id"]:
                    continue
                score = start_distance + end_distance
                if score < best_score:
                    best_score = score
                    best_pair = (start_attachment, end_attachment, start_distance, end_distance)
        return best_pair

    routes: list[ConnectorRoute] = []
    best_routes: dict[tuple[str, str], ConnectorRoute] = {}
    pair_support_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
    for path in ortho_paths:
        if len(path) < 2:
            continue
        attachment_pair = best_attachment_pair(path)
        if attachment_pair is None:
            continue
        start_attachment, end_attachment, start_distance, end_distance = attachment_pair

        node_pair = tuple(sorted([start_attachment["node_id"], end_attachment["node_id"]]))
        pair_support_counts[node_pair] += 1
        start_id = start_attachment["graph_vertex_id"]
        end_id = end_attachment["graph_vertex_id"]
        chosen_path = shortest_path(start_id, end_id)
        if chosen_path is None or len(chosen_path) < 2:
            continue

        points = [start_attachment["gate_point"]]
        path_points = [vertex_lookup[vertex_id] for vertex_id in chosen_path]
        if path_points:
            start_elbow = _orthogonal_gate_elbow(
                start_attachment["gate_point"],
                path_points[0],
                str(start_attachment["side"]),
            )
            if start_elbow != points[-1] and start_elbow != path_points[0]:
                points.append(start_elbow)
        for point in path_points:
            if point != points[-1]:
                points.append(point)
        if path_points:
            end_elbow = _orthogonal_gate_elbow(
                end_attachment["gate_point"],
                path_points[-1],
                str(end_attachment["side"]),
            )
            if end_elbow != points[-1] and end_elbow != end_attachment["gate_point"]:
                points.append(end_elbow)
        if end_attachment["gate_point"] != points[-1]:
            points.append(end_attachment["gate_point"])
        cleaned_points, cleanup_debug = cleanup_route_shape(
            points,
            src_side=str(start_attachment["side"]),
            dst_side=str(end_attachment["side"]),
            micro_bend_threshold=micro_bend_threshold,
            axis_snap_tolerance=axis_snap_tolerance,
        )
        candidate = ConnectorRoute(
            id="",
            src_node_id=start_attachment["node_id"],
            src_side=start_attachment["side"],
            dst_node_id=end_attachment["node_id"],
            dst_side=end_attachment["side"],
            vertex_path=chosen_path,
            points=cleaned_points,
            confidence=0.8,
            ambiguous=False,
                debug={
                    "simplified_edge_count": max(len(chosen_path) - 1, 0),
                    "fallback_used": False,
                    "unsimplified_component_rejected": False,
                    "attachment_pair": [start_attachment["graph_vertex_id"], end_attachment["graph_vertex_id"]],
                    "attachment_distances": [round(start_distance, 2), round(end_distance, 2)],
                    "attachment_distance_sum": round(start_distance + end_distance, 2),
                    "stub_absorbed": bool(start_attachment.get("stub_absorbed")) or bool(end_attachment.get("stub_absorbed")),
                    **cleanup_debug,
                },
            )
        existing = best_routes.get(node_pair)
        if existing is None or len(candidate.vertex_path) < len(existing.vertex_path):
            best_routes[node_pair] = candidate

    kept_routes = []
    for route in best_routes.values():
        node_pair = tuple(sorted((route.src_node_id, route.dst_node_id)))
        support_count = pair_support_counts[node_pair]
        if _keep_route_candidate(route, support_count):
            kept_routes.append(route)
    for index, route in enumerate(kept_routes, start=1):
        node_pair = tuple(sorted((route.src_node_id, route.dst_node_id)))
        route.debug["support_count"] = pair_support_counts[node_pair]
        route.id = f"route_{index:03d}"
        routes.append(route)
    return routes


def graph_sanity(
    vertices: list[GraphVertex],
    edges: list[GraphEdge],
    reduced_degree2_vertices: int,
    pruned_spurs: int,
    collapsed_corridor_groups: int,
    warn_vertices: int,
    fail_vertices: int,
    warn_edges: int,
    fail_edges: int,
) -> GraphDiagnostics:
    vertex_count = len(vertices)
    edge_count = len(edges)
    status = "pass"
    reason = None
    if vertex_count > fail_vertices or edge_count > fail_edges:
        status = "fail"
        reason = "graph_over_fragmented"
    elif vertex_count > warn_vertices or edge_count > warn_edges:
        status = "warn"
        reason = "graph_still_dense"
    return GraphDiagnostics(
        vertex_count=vertex_count,
        edge_count=edge_count,
        reduced_degree2_vertices=reduced_degree2_vertices,
        pruned_spurs=pruned_spurs,
        collapsed_corridor_groups=collapsed_corridor_groups,
        status=status,
        reason=reason,
    )


def run_simplification_self_test() -> None:
    segments = [
        OrthoSegment(id="t1", orientation="H", x1=10, y1=50, x2=30, y2=50, component_id="test"),
        OrthoSegment(id="t2", orientation="H", x1=12, y1=52, x2=32, y2=52, component_id="test"),
        OrthoSegment(id="t3", orientation="H", x1=11, y1=49, x2=31, y2=49, component_id="test"),
        OrthoSegment(id="t4", orientation="H", x1=9, y1=51, x2=29, y2=51, component_id="test"),
        OrthoSegment(id="t5", orientation="H", x1=8, y1=50, x2=33, y2=50, component_id="test"),
    ]
    working = normalize_ortho_segments(segments, axis_snap_tolerance=1)
    working = iterative_collinear_merge(working, merge_gap_tolerance=18, parallel_offset_tolerance=0)
    working, collapsed_groups, _ = collapse_parallel_corridors(working, overlap_ratio_min=0.2, parallel_distance_max=4, min_group_size=2)
    working = filter_dominant_segments(working, parallel_offset_tolerance=3)
    if collapsed_groups <= 0:
        raise RuntimeError("Synthetic corridor-collapse self-test failed: no corridor groups collapsed")
    if len(working) != 1:
        raise RuntimeError(f"Synthetic corridor-collapse self-test failed: expected 1 segment, got {len(working)}")
    graph_vertices, graph_edges, _, _ = build_graph(working, np.zeros((100, 100), dtype=np.uint8), continuity_radius=2, endpoint_intersection_tolerance=8)
    graph_vertices, graph_edges, removed, _ = reduce_degree2_vertices(graph_vertices, graph_edges)
    if len(graph_vertices) != 2 or len(graph_edges) != 1 or removed != 0:
        raise RuntimeError(
            f"Synthetic graph self-test failed: expected 2 vertices/1 edge/0 removed, got {len(graph_vertices)}/{len(graph_edges)}/{removed}"
        )

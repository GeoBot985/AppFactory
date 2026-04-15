from __future__ import annotations

import math

import cv2
import numpy as np

from .grid import snap_point, snap_points
from .models import Connector, Element, InterpretedGeometry, Node, RawGeometry


def contour_to_points(contour: np.ndarray) -> list[tuple[int, int]]:
    return snap_points([(int(p[0][0]), int(p[0][1])) for p in contour])


def simplify_contour(contour: np.ndarray, epsilon_ratio: float) -> np.ndarray:
    perimeter = cv2.arcLength(contour, True)
    epsilon = max(1.0, perimeter * epsilon_ratio)
    return cv2.approxPolyDP(contour, epsilon, True)


def bbox_and_center(points: list[tuple[int, int]]) -> tuple[tuple[int, int, int, int], tuple[int, int]]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    bbox = (int(min_x), int(min_y), int(max_x - min_x), int(max_y - min_y))
    center = (int(round((min_x + max_x) / 2)), int(round((min_y + max_y) / 2)))
    return bbox, center


def classify_shape(contour: np.ndarray, simplified: np.ndarray) -> tuple[str, float]:
    area = cv2.contourArea(contour)
    perimeter = cv2.arcLength(contour, True)
    if area <= 0 or perimeter <= 0:
        return "unknown-shape", 0.2

    approx_vertices = len(simplified)
    x, y, w, h = cv2.boundingRect(contour)
    bbox_area = max(w * h, 1)
    fill_ratio = area / bbox_area
    circularity = (4.0 * math.pi * area) / max(perimeter * perimeter, 1.0)

    if approx_vertices == 4 and fill_ratio >= 0.55:
        return "rectangle-like", 0.9
    if approx_vertices >= 8 and circularity >= 0.68:
        return "ellipse-like", 0.78
    if 3 <= approx_vertices <= 10:
        return "polygon-like", 0.7
    return "unknown-shape", 0.35


def classify_path(is_closed: bool) -> tuple[str, float]:
    if is_closed:
        return "closed-path", 0.7
    return "polyline", 0.72


def build_shape_element(
    element_id: str,
    contour: np.ndarray,
    epsilon_ratio: float,
) -> Element:
    simplified = simplify_contour(contour, epsilon_ratio)
    raw_points = contour_to_points(contour)
    render_points = contour_to_points(simplified)
    bbox, center = bbox_and_center(render_points or raw_points)
    shape_type, confidence = classify_shape(contour, simplified)
    raw_geometry = RawGeometry(
        outline_points=raw_points,
        contour_area=int(round(cv2.contourArea(contour))),
        perimeter=int(round(cv2.arcLength(contour, True))),
    )
    interpreted_geometry = InterpretedGeometry(
        shape_type=shape_type,
        render_points=render_points,
        closed=True,
    )
    return Element(
        id=element_id,
        element_type="shape_candidate",
        raw_geometry=raw_geometry,
        interpreted_geometry=interpreted_geometry,
        bbox=bbox,
        center=center,
        confidence=round(confidence, 3),
        debug={"approx_vertices": len(simplified)},
    )


def build_connector_element(
    element_id: str,
    points: list[tuple[int, int]],
    closed: bool,
) -> Element:
    snapped_points = snap_points(points)
    bbox, center = bbox_and_center(snapped_points)
    path_type, confidence = classify_path(closed)
    raw_geometry = RawGeometry(
        path_points=snapped_points,
        perimeter=int(
            round(
                sum(
                    math.dist(snapped_points[i], snapped_points[i + 1])
                    for i in range(len(snapped_points) - 1)
                )
            )
        ),
    )
    interpreted_geometry = InterpretedGeometry(
        path_type=path_type,
        render_points=snapped_points,
        closed=closed,
    )
    return Element(
        id=element_id,
        element_type="connector_candidate",
        raw_geometry=raw_geometry,
        interpreted_geometry=interpreted_geometry,
        bbox=bbox,
        center=center,
        confidence=round(confidence, 3),
        debug={"point_count": len(snapped_points)},
    )


def build_unknown_element(
    element_id: str,
    contour: np.ndarray,
    epsilon_ratio: float,
) -> Element:
    simplified = simplify_contour(contour, epsilon_ratio)
    raw_points = contour_to_points(contour)
    render_points = contour_to_points(simplified)
    bbox, center = bbox_and_center(render_points or raw_points)
    raw_geometry = RawGeometry(
        outline_points=raw_points,
        contour_area=int(round(cv2.contourArea(contour))),
        perimeter=int(round(cv2.arcLength(contour, True))),
    )
    interpreted_geometry = InterpretedGeometry(
        shape_type="unknown-shape",
        render_points=render_points,
        closed=bool(cv2.isContourConvex(simplified)),
    )
    return Element(
        id=element_id,
        element_type="unknown_candidate",
        raw_geometry=raw_geometry,
        interpreted_geometry=interpreted_geometry,
        bbox=bbox,
        center=center,
        confidence=0.25,
        debug={"approx_vertices": len(simplified)},
    )


def build_line_path(points: np.ndarray) -> list[tuple[int, int]]:
    reshaped = points.reshape(-1, 2)
    return [snap_point((int(x), int(y))) for x, y in reshaped]


def bbox_contains(outer: tuple[int, int, int, int], inner: tuple[int, int, int, int], margin: int = 0) -> bool:
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return (
        ix >= ox + margin
        and iy >= oy + margin
        and ix + iw <= ox + ow - margin
        and iy + ih <= oy + oh - margin
    )


def bbox_iou(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
    ax1, ay1, aw, ah = first
    bx1, by1, bw, bh = second
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    inter_w = max(0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0, min(ay2, by2) - max(ay1, by1))
    inter_area = inter_w * inter_h
    if inter_area <= 0:
        return 0.0
    union = aw * ah + bw * bh - inter_area
    return inter_area / max(union, 1)


def expand_bbox(
    bbox: tuple[int, int, int, int],
    outward_padding: int,
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int]:
    x, y, w, h = bbox
    min_x = max(0, x - outward_padding)
    min_y = max(0, y - outward_padding)
    max_x = min(image_width - 1, x + w + outward_padding)
    max_y = min(image_height - 1, y + h + outward_padding)
    return min_x, min_y, max_x - min_x, max_y - min_y


def _gate_half_span(bbox: tuple[int, int, int, int], min_span: int, max_span: int) -> int:
    _, _, w, h = bbox
    return int(max(min_span, min(max_span, round(min(w, h) * 0.18))))


def build_node_from_element(
    node_id: str,
    element: Element,
    image_width: int,
    image_height: int,
    outward_padding: int,
    label_height_ratio: float,
    gate_min_span: int,
    gate_max_span: int,
) -> Node:
    x, y, w, h = element.bbox
    center = (x + w // 2, y + h // 2)
    side_midpoints = {
        "top": (x + w // 2, y),
        "right": (x + w, y + h // 2),
        "bottom": (x + w // 2, y + h),
        "left": (x, y + h // 2),
    }
    gate_half_span = _gate_half_span(element.bbox, gate_min_span, gate_max_span)
    gates = {side: point for side, point in side_midpoints.items()}
    gate_segments = {
        "top": [(gates["top"][0] - gate_half_span, y), (gates["top"][0] + gate_half_span, y)],
        "bottom": [(gates["bottom"][0] - gate_half_span, y + h), (gates["bottom"][0] + gate_half_span, y + h)],
        "left": [(x, gates["left"][1] - gate_half_span), (x, gates["left"][1] + gate_half_span)],
        "right": [(x + w, gates["right"][1] - gate_half_span), (x + w, gates["right"][1] + gate_half_span)],
    }
    label_height = max(12, int(round(h * label_height_ratio)))
    label_region = (x + 4, y + 4, max(w - 8, 1), max(min(label_height, h - 8), 1))
    return Node(
        id=node_id,
        bbox=element.bbox,
        center=center,
        side_midpoints=side_midpoints,
        expanded_bbox=expand_bbox(element.bbox, outward_padding, image_width, image_height),
        label_region=label_region,
        gates=gates,
        gate_segments=gate_segments,
        debug={
            "source_element_id": element.id,
            "shape_type": element.interpreted_geometry.shape_type,
            "frozen": True,
        },
    )


def build_connector(
    connector_id: str,
    points: list[tuple[int, int]],
    src_node_id: str | None,
    src_side: str | None,
    dst_node_id: str | None,
    dst_side: str | None,
    confidence: float,
    debug: dict[str, object] | None = None,
) -> Connector:
    return Connector(
        id=connector_id,
        points=snap_points(points),
        src_node_id=src_node_id,
        src_side=src_side,
        dst_node_id=dst_node_id,
        dst_side=dst_side,
        confidence=round(confidence, 3),
        debug=debug or {},
    )

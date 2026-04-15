from __future__ import annotations

import math

import cv2

from .geometry import build_connector_element, build_shape_element, build_unknown_element
from .models import Element
from .separation import SeparationCandidate


def _segment_length(path: list[tuple[int, int]]) -> float:
    return math.dist(path[0], path[-1])


def _segment_angle(path: list[tuple[int, int]]) -> float:
    dx = path[-1][0] - path[0][0]
    dy = path[-1][1] - path[0][1]
    return math.degrees(math.atan2(dy, dx))


def _segment_midpoint(path: list[tuple[int, int]]) -> tuple[float, float]:
    return ((path[0][0] + path[-1][0]) / 2.0, (path[0][1] + path[-1][1]) / 2.0)


def _is_duplicate_path(
    path: list[tuple[int, int]],
    existing_paths: list[list[tuple[int, int]]],
    midpoint_tolerance: float = 10.0,
    angle_tolerance: float = 8.0,
    length_ratio_tolerance: float = 0.2,
) -> bool:
    candidate_mid = _segment_midpoint(path)
    candidate_angle = _segment_angle(path)
    candidate_length = max(_segment_length(path), 1.0)

    for existing in existing_paths:
        existing_mid = _segment_midpoint(existing)
        existing_angle = _segment_angle(existing)
        existing_length = max(_segment_length(existing), 1.0)
        midpoint_distance = math.dist(candidate_mid, existing_mid)
        angle_delta = abs(candidate_angle - existing_angle)
        angle_delta = min(angle_delta, abs(angle_delta - 180.0))
        length_delta_ratio = abs(candidate_length - existing_length) / max(candidate_length, existing_length)
        if (
            midpoint_distance <= midpoint_tolerance
            and angle_delta <= angle_tolerance
            and length_delta_ratio <= length_ratio_tolerance
        ):
            return True
    return False


def extract_primitives(
    shape_candidates: list[SeparationCandidate],
    connector_paths: list[list[tuple[int, int]]],
    connector_group_ids: list[int],
    min_contour_area: int,
    contour_epsilon_ratio: float,
    min_connector_path_length: int,
) -> tuple[list[Element], list, list[list[tuple[int, int]]]]:
    elements: list[Element] = []
    kept_contours: list = []

    shape_index = 1
    unknown_index = 1

    for candidate in shape_candidates:
        contour = candidate.contour
        area = cv2.contourArea(contour)
        if area < min_contour_area:
            continue

        kept_contours.append(contour)
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, max(1.0, perimeter * contour_epsilon_ratio), True)
        is_closed = len(approx) >= 3

        debug = {
            "source_mask": "shape_mask",
            "parent_shape_id": candidate.parent_shape_id,
            "is_internal_noise": False,
            "rejection_reason": None,
            "separation_metrics": candidate.metrics,
        }

        if is_closed:
            element = build_shape_element(f"shape_{shape_index:03d}", contour, contour_epsilon_ratio)
            element.debug.update(debug)
            elements.append(element)
            shape_index += 1
        else:
            element = build_unknown_element(f"unknown_{unknown_index:03d}", contour, contour_epsilon_ratio)
            element.debug.update(debug)
            elements.append(element)
            unknown_index += 1

    line_paths: list[list[tuple[int, int]]] = []
    connector_index = 1
    for path, group_id in zip(connector_paths, connector_group_ids):
        if len(path) < 2:
            continue
        if _segment_length(path) < float(min_connector_path_length):
            continue
        if _is_duplicate_path(path, line_paths):
            continue
        line_paths.append(path)
        element = build_connector_element(f"connector_{connector_index:03d}", path, closed=False)
        element.debug.update(
            {
                "source_mask": "line_mask",
                "parent_shape_id": None,
                "is_internal_noise": False,
                "merge_group_id": int(group_id),
                "rejection_reason": None,
                "separation_metrics": {
                    "line_length": round(_segment_length(path), 2),
                    "aspect_ratio": round(
                        max(abs(path[-1][0] - path[0][0]), abs(path[-1][1] - path[0][1]))
                        / max(min(max(abs(path[-1][0] - path[0][0]), 1), max(abs(path[-1][1] - path[0][1]), 1)), 1),
                        4,
                    ),
                    "bbox_fill_ratio": 0.0,
                    "border_touch_count": 0,
                },
            }
        )
        elements.append(element)
        connector_index += 1

    return elements, kept_contours, line_paths

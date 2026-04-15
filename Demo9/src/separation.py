from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class SeparationCandidate:
    contour: np.ndarray
    metrics: dict[str, int | float]
    bbox: tuple[int, int, int, int]
    candidate_index: int
    parent_index: int | None = None
    parent_shape_id: str | None = None
    is_internal_noise: bool = False
    rejection_reason: str | None = None


@dataclass
class SeparationResult:
    shape_mask: np.ndarray
    line_mask: np.ndarray
    artifact_mask: np.ndarray
    shapes_subtracted_mask: np.ndarray
    shape_candidates_before_filter: list[SeparationCandidate]
    shape_candidates: list[SeparationCandidate]
    rejected_candidates: list[SeparationCandidate]
    internal_noise_candidates: list[SeparationCandidate]
    summary: dict[str, int]


def _border_touch_count(bbox: tuple[int, int, int, int], image_width: int, image_height: int, margin: int) -> int:
    x, y, w, h = bbox
    count = 0
    if x <= margin:
        count += 1
    if y <= margin:
        count += 1
    if x + w >= image_width - margin:
        count += 1
    if y + h >= image_height - margin:
        count += 1
    return count


def _bbox_contains(
    outer: tuple[int, int, int, int],
    inner: tuple[int, int, int, int],
    margin: int,
) -> bool:
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return (
        ix >= ox + margin
        and iy >= oy + margin
        and ix + iw <= ox + ow - margin
        and iy + ih <= oy + oh - margin
    )


def _candidate_metrics(contour: np.ndarray, image_width: int, image_height: int, border_margin: int) -> tuple[dict[str, int | float], tuple[int, int, int, int]]:
    area = float(cv2.contourArea(contour))
    perimeter = float(cv2.arcLength(contour, True))
    x, y, w, h = cv2.boundingRect(contour)
    bbox_area = max(w * h, 1)
    aspect_ratio = max(w, h) / max(min(w, h), 1)
    metrics = {
        "contour_area": int(round(area)),
        "bbox_area": int(bbox_area),
        "bbox_fill_ratio": round(area / bbox_area, 4),
        "perimeter": int(round(perimeter)),
        "aspect_ratio": round(aspect_ratio, 4),
        "border_touch_count": _border_touch_count((x, y, w, h), image_width, image_height, border_margin),
        "bbox_width_ratio": round(w / max(image_width, 1), 4),
        "bbox_height_ratio": round(h / max(image_height, 1), 4),
        "bbox_width": int(w),
        "bbox_height": int(h),
    }
    return metrics, (x, y, w, h)


def _artifact_reason(
    metrics: dict[str, int | float],
    image_area: int,
    max_shape_area_ratio: float,
    extreme_span_ratio: float,
    border_touch_reject_count: int,
    frame_fill_ratio_threshold: float,
) -> str | None:
    if float(metrics["contour_area"]) > image_area * max_shape_area_ratio:
        return "area_exceeds_threshold"
    if (
        float(metrics["bbox_width_ratio"]) >= extreme_span_ratio
        and float(metrics["bbox_height_ratio"]) >= extreme_span_ratio
    ):
        return "bbox_spans_most_of_image"
    if int(metrics["border_touch_count"]) >= border_touch_reject_count:
        return "touches_multiple_borders"
    if (
        int(metrics["border_touch_count"]) >= 2
        and float(metrics["bbox_fill_ratio"]) <= frame_fill_ratio_threshold
        and float(metrics["bbox_width_ratio"]) >= 0.75
    ):
        return "likely_enclosing_frame"
    return None


def _assign_parent_relationships(
    candidates: list[SeparationCandidate],
    containment_margin: int,
) -> None:
    sorted_candidates = sorted(candidates, key=lambda candidate: candidate.metrics["bbox_area"], reverse=True)
    for candidate in sorted_candidates:
        parent = None
        for maybe_parent in sorted_candidates:
            if maybe_parent.candidate_index == candidate.candidate_index:
                continue
            if int(maybe_parent.metrics["bbox_area"]) <= int(candidate.metrics["bbox_area"]):
                continue
            if _bbox_contains(maybe_parent.bbox, candidate.bbox, containment_margin):
                parent = maybe_parent
                break
        if parent is not None:
            candidate.parent_index = parent.candidate_index


def _internal_noise_reason(
    candidate: SeparationCandidate,
    parent: SeparationCandidate | None,
    small_box_area_limit: int,
    text_like_max_height: int,
    text_like_aspect_ratio: float,
    child_area_ratio_threshold: float,
    child_bbox_area_ratio_threshold: float,
) -> str | None:
    if parent is None:
        return None

    child_area = float(candidate.metrics["contour_area"])
    parent_area = max(float(parent.metrics["contour_area"]), 1.0)
    child_bbox_area = float(candidate.metrics["bbox_area"])
    parent_bbox_area = max(float(parent.metrics["bbox_area"]), 1.0)
    bbox_height = int(candidate.metrics["bbox_height"])
    bbox_width = int(candidate.metrics["bbox_width"])
    aspect_ratio = float(candidate.metrics["aspect_ratio"])

    if child_area <= small_box_area_limit and bbox_height <= text_like_max_height and bbox_width <= text_like_max_height * 6:
        return "too_small_and_enclosed"
    if bbox_height <= text_like_max_height and aspect_ratio >= text_like_aspect_ratio:
        return "text_like_small_contour"
    if child_area / parent_area <= child_area_ratio_threshold and child_bbox_area / parent_bbox_area <= child_bbox_area_ratio_threshold:
        return "internal_noise_inside_parent_shape"
    return None


def separate_geometry(
    binary: np.ndarray,
    edges: np.ndarray,
    shape_close_kernel_size: int,
    shape_dilate_kernel_size: int,
    min_shape_area: int,
    max_shape_area_ratio: float,
    artifact_border_margin: int,
    artifact_border_touch_reject_count: int,
    artifact_extreme_span_ratio: float,
    artifact_frame_fill_ratio_threshold: float,
    internal_containment_margin: int,
    internal_small_box_area_limit: int,
    internal_text_like_max_height: int,
    internal_text_like_aspect_ratio: float,
    internal_child_area_ratio_threshold: float,
    internal_child_bbox_area_ratio_threshold: float,
) -> SeparationResult:
    image_height, image_width = binary.shape[:2]
    image_area = image_width * image_height

    shape_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (shape_close_kernel_size, shape_close_kernel_size))
    dilate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (shape_dilate_kernel_size, shape_dilate_kernel_size))

    closed_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, shape_kernel)
    contours, _ = cv2.findContours(closed_edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    artifact_mask = np.zeros_like(binary)
    shapes_before_mask = np.zeros_like(binary)
    filtered_shape_mask = np.zeros_like(binary)

    provisional_candidates: list[SeparationCandidate] = []
    rejected_candidates: list[SeparationCandidate] = []
    internal_noise_candidates: list[SeparationCandidate] = []

    for index, contour in enumerate(contours):
        metrics, bbox = _candidate_metrics(contour, image_width, image_height, artifact_border_margin)
        if int(metrics["contour_area"]) < min_shape_area:
            rejected_candidates.append(
                SeparationCandidate(
                    contour=contour,
                    metrics=metrics,
                    bbox=bbox,
                    candidate_index=index,
                    rejection_reason="below_min_shape_area",
                )
            )
            continue

        rejection_reason = _artifact_reason(
            metrics=metrics,
            image_area=image_area,
            max_shape_area_ratio=max_shape_area_ratio,
            extreme_span_ratio=artifact_extreme_span_ratio,
            border_touch_reject_count=artifact_border_touch_reject_count,
            frame_fill_ratio_threshold=artifact_frame_fill_ratio_threshold,
        )
        candidate = SeparationCandidate(
            contour=contour,
            metrics=metrics,
            bbox=bbox,
            candidate_index=index,
            rejection_reason=rejection_reason,
        )
        if rejection_reason is None:
            provisional_candidates.append(candidate)
            cv2.drawContours(shapes_before_mask, [contour], -1, 255, thickness=2)
        else:
            rejected_candidates.append(candidate)
            cv2.drawContours(artifact_mask, [contour], -1, 255, thickness=cv2.FILLED)

    _assign_parent_relationships(provisional_candidates, internal_containment_margin)
    candidates_by_index = {candidate.candidate_index: candidate for candidate in provisional_candidates}

    kept_candidates: list[SeparationCandidate] = []
    for candidate in sorted(provisional_candidates, key=lambda item: item.metrics["bbox_area"], reverse=True):
        parent = candidates_by_index.get(candidate.parent_index) if candidate.parent_index is not None else None
        if parent is not None:
            candidate.parent_shape_id = f"shape_candidate_{parent.candidate_index:03d}"
        reason = _internal_noise_reason(
            candidate=candidate,
            parent=parent,
            small_box_area_limit=internal_small_box_area_limit,
            text_like_max_height=internal_text_like_max_height,
            text_like_aspect_ratio=internal_text_like_aspect_ratio,
            child_area_ratio_threshold=internal_child_area_ratio_threshold,
            child_bbox_area_ratio_threshold=internal_child_bbox_area_ratio_threshold,
        )
        if reason is not None:
            candidate.rejection_reason = reason
            candidate.is_internal_noise = True
            internal_noise_candidates.append(candidate)
            cv2.drawContours(artifact_mask, [candidate.contour], -1, 255, thickness=cv2.FILLED)
            continue
        kept_candidates.append(candidate)
        cv2.drawContours(filtered_shape_mask, [candidate.contour], -1, 255, thickness=2)

    shape_mask = cv2.dilate(filtered_shape_mask, dilate_kernel, iterations=1)
    filled_shape_mask = np.zeros_like(binary)
    for candidate in kept_candidates:
        cv2.drawContours(filled_shape_mask, [candidate.contour], -1, 255, thickness=cv2.FILLED)

    inner_shape_mask = cv2.erode(filled_shape_mask, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)), iterations=1)
    shapes_subtracted_mask = cv2.bitwise_and(binary, cv2.bitwise_not(inner_shape_mask))
    edge_lines = cv2.bitwise_and(edges, cv2.bitwise_not(inner_shape_mask))
    line_mask = cv2.bitwise_or(shapes_subtracted_mask, edge_lines)
    line_mask = cv2.bitwise_and(line_mask, cv2.bitwise_not(artifact_mask))

    return SeparationResult(
        shape_mask=shape_mask,
        line_mask=line_mask,
        artifact_mask=artifact_mask,
        shapes_subtracted_mask=shapes_subtracted_mask,
        shape_candidates_before_filter=provisional_candidates,
        shape_candidates=kept_candidates,
        rejected_candidates=rejected_candidates,
        internal_noise_candidates=internal_noise_candidates,
        summary={
            "raw_contours_found": len(contours),
            "shape_candidates_before_internal_filter": len(provisional_candidates),
            "shape_mask_contours_found": len(kept_candidates),
            "artifacts_rejected": len(rejected_candidates),
            "internal_noise_rejected": len(internal_noise_candidates),
        },
    )

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field

from models import Node, Rect


@dataclass(slots=True)
class RenderConfig:
    min_draw_area_px: float = 9.0
    min_border_area_px: float = 150.0
    min_label_area_px: float = 3000.0
    min_label_width_px: float = 60.0
    min_label_height_px: float = 18.0
    min_folder_container_area_px: float = 500.0
    depth_factor: float = 0.25


@dataclass(slots=True)
class DrawPolicy:
    draw_fill: bool
    draw_border: bool
    draw_label: bool
    skip_reason: str | None = None


@dataclass(slots=True)
class RenderMetrics:
    total_nodes_considered: int = 0
    rectangles_drawn: int = 0
    labels_drawn: int = 0
    borders_drawn: int = 0
    nodes_skipped_due_to_area: int = 0
    folder_containers_suppressed: int = 0
    borders_omitted: int = 0

    def summary(self) -> str:
        return (
            f"Render: {self.rectangles_drawn} rects, {self.labels_drawn} labels, "
            f"{self.borders_drawn} borders, {self.nodes_skipped_due_to_area} skipped"
        )


@dataclass(slots=True)
class RenderState:
    rects: list[Rect]
    item_to_rect: dict[int, Rect]
    metrics: RenderMetrics = field(default_factory=RenderMetrics)


class TreemapRenderer:
    def __init__(
        self,
        canvas: tk.Canvas,
        show_labels: bool = True,
        config: RenderConfig | None = None,
    ) -> None:
        self.canvas = canvas
        self.show_labels = show_labels
        self.config = config or RenderConfig()
        self.state = RenderState(rects=[], item_to_rect={})
        self.selected_item: int | None = None
        self.hover_item: int | None = None

    def draw(self, rects: list[Rect], selected_node: Node | None = None) -> RenderMetrics:
        self.canvas.delete("all")
        item_to_rect: dict[int, Rect] = {}
        metrics = RenderMetrics()
        self.state = RenderState(rects=rects, item_to_rect=item_to_rect, metrics=metrics)
        self.selected_item = None
        self.hover_item = None

        ordered = sorted(rects, key=lambda rect: rect.depth)
        for rect in ordered:
            policy = evaluate_draw_policy(rect, self.config, self.show_labels)
            _record_policy_metrics(metrics, rect, policy)
            if not policy.draw_fill:
                continue

            outline = ""
            width = 0
            if policy.draw_border:
                outline = _border_color_for_depth(rect.depth)
                width = 1

            item_id = self.canvas.create_rectangle(
                rect.x,
                rect.y,
                rect.x + rect.w,
                rect.y + rect.h,
                fill=rect.fill,
                outline=outline,
                width=width,
            )
            item_to_rect[item_id] = rect

            if policy.draw_label:
                self.canvas.create_text(
                    rect.x + 4,
                    rect.y + 4,
                    text=_build_label(rect),
                    anchor="nw",
                    fill="#ffffff",
                    font=("Segoe UI", 9, "bold" if rect.depth == 0 else "normal"),
                    width=max(0.0, rect.w - 8),
                )

            if selected_node is not None and rect.node is selected_node:
                self.selected_item = item_id
                self.canvas.itemconfigure(item_id, outline="#111827", width=3)

        print(self.state.metrics.summary())
        return self.state.metrics

    def set_show_labels(self, enabled: bool) -> None:
        self.show_labels = enabled

    def rect_at(self, x: int, y: int) -> Rect | None:
        current = self.canvas.find_overlapping(x, y, x, y)
        for item_id in reversed(current):
            rect = self.state.item_to_rect.get(item_id)
            if rect is not None:
                return rect
        return None

    def highlight_hover(self, rect: Rect | None) -> None:
        if self.hover_item is not None and self.hover_item in self.state.item_to_rect:
            self._restore_outline(self.hover_item)
        self.hover_item = None
        if rect is None:
            return
        for item_id, candidate in self.state.item_to_rect.items():
            if candidate is rect:
                self.hover_item = item_id
                if item_id != self.selected_item:
                    self.canvas.itemconfigure(item_id, outline="#111827", width=2)
                break

    def select(self, rect: Rect | None) -> None:
        if self.selected_item is not None and self.selected_item in self.state.item_to_rect:
            self._restore_outline(self.selected_item)
        self.selected_item = None
        if rect is None:
            return
        for item_id, candidate in self.state.item_to_rect.items():
            if candidate is rect:
                self.selected_item = item_id
                self.canvas.itemconfigure(item_id, outline="#111827", width=3)
                break

    def _restore_outline(self, item_id: int) -> None:
        rect = self.state.item_to_rect.get(item_id)
        if rect is None:
            return
        policy = evaluate_draw_policy(rect, self.config, self.show_labels)
        outline = _border_color_for_depth(rect.depth) if policy.draw_border else ""
        width = 1 if policy.draw_border else 0
        self.canvas.itemconfigure(item_id, outline=outline, width=width)


def evaluate_draw_policy(rect: Rect, config: RenderConfig, show_labels: bool) -> DrawPolicy:
    area = rect.w * rect.h
    if area < config.min_draw_area_px:
        return DrawPolicy(draw_fill=False, draw_border=False, draw_label=False, skip_reason="area")

    border_threshold = _depth_scaled(config.min_border_area_px, rect.depth, config.depth_factor)
    folder_threshold = _depth_scaled(
        config.min_folder_container_area_px,
        rect.depth,
        config.depth_factor,
    )
    label_threshold = _depth_scaled(config.min_label_area_px, rect.depth, config.depth_factor)

    draw_border = area >= border_threshold
    if rect.node.is_dir and area < folder_threshold:
        draw_border = False

    draw_label = (
        show_labels
        and area >= label_threshold
        and rect.w >= config.min_label_width_px
        and rect.h >= config.min_label_height_px
    )
    return DrawPolicy(draw_fill=True, draw_border=draw_border, draw_label=draw_label)


def _record_policy_metrics(metrics: RenderMetrics, rect: Rect, policy: DrawPolicy) -> None:
    metrics.total_nodes_considered += 1
    if not policy.draw_fill:
        metrics.nodes_skipped_due_to_area += 1
        return

    metrics.rectangles_drawn += 1
    if policy.draw_label:
        metrics.labels_drawn += 1
    if policy.draw_border:
        metrics.borders_drawn += 1
    else:
        metrics.borders_omitted += 1
        if rect.node.is_dir:
            metrics.folder_containers_suppressed += 1


def _depth_scaled(base_threshold: float, depth: int, depth_factor: float) -> float:
    return base_threshold * (1.0 + depth * depth_factor)


def _border_color_for_depth(depth: int) -> str:
    return "#d1d5db" if depth == 0 else "#f3f4f6"


def _build_label(rect: Rect) -> str:
    return rect.node.display_name

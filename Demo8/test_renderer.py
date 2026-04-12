from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from models import Node, Rect
from renderer import RenderConfig, TreemapRenderer, evaluate_draw_policy


class FakeCanvas:
    def __init__(self) -> None:
        self.items: dict[int, dict[str, object]] = {}
        self.next_id = 1

    def delete(self, _tag: str) -> None:
        self.items.clear()

    def create_rectangle(self, x1, y1, x2, y2, **kwargs):
        item_id = self.next_id
        self.next_id += 1
        self.items[item_id] = {"kind": "rect", "coords": (x1, y1, x2, y2), **kwargs}
        return item_id

    def create_text(self, x, y, **kwargs):
        item_id = self.next_id
        self.next_id += 1
        self.items[item_id] = {"kind": "text", "coords": (x, y), **kwargs}
        return item_id

    def itemconfigure(self, item_id: int, **kwargs) -> None:
        self.items[item_id].update(kwargs)

    def find_overlapping(self, x1, y1, x2, y2):
        hits: list[int] = []
        for item_id, item in self.items.items():
            if item["kind"] != "rect":
                continue
            left, top, right, bottom = item["coords"]
            if not (x2 < left or x1 > right or y2 < top or y1 > bottom):
                hits.append(item_id)
        return tuple(hits)


def test_draw_policy_skips_tiny_nodes() -> None:
    policy = evaluate_draw_policy(_rect(2, 3, depth=1), RenderConfig(), show_labels=True)
    assert policy.draw_fill is False
    assert policy.draw_border is False
    assert policy.draw_label is False


def test_depth_adjusted_thresholds_become_stricter() -> None:
    config = RenderConfig(min_border_area_px=100, depth_factor=0.25)
    shallow = evaluate_draw_policy(_rect(11, 10, depth=0), config, show_labels=True)
    deep = evaluate_draw_policy(_rect(11, 10, depth=3), config, show_labels=True)
    assert shallow.draw_border is True
    assert deep.draw_border is False


def test_label_suppression_requires_area_and_dimensions() -> None:
    config = RenderConfig(min_label_area_px=3000, min_label_width_px=60, min_label_height_px=18)
    assert evaluate_draw_policy(_rect(80, 40, depth=0), config, show_labels=True).draw_label is True
    assert evaluate_draw_policy(_rect(59, 80, depth=0), config, show_labels=True).draw_label is False
    assert evaluate_draw_policy(_rect(80, 17, depth=0), config, show_labels=True).draw_label is False


def test_folder_container_border_suppression() -> None:
    config = RenderConfig(min_border_area_px=150, min_folder_container_area_px=500)
    folder_rect = _rect(20, 20, depth=1, is_dir=True)
    file_rect = _rect(20, 20, depth=1, is_dir=False)
    assert evaluate_draw_policy(folder_rect, config, show_labels=True).draw_border is False
    assert evaluate_draw_policy(file_rect, config, show_labels=True).draw_border is True


def test_renderer_metrics_track_skips_borders_and_labels() -> None:
    canvas = FakeCanvas()
    renderer = TreemapRenderer(canvas, config=RenderConfig())
    rects = [
        _rect(100, 80, depth=0, name="root", is_dir=True),
        _rect(80, 50, depth=1, name="big-file", is_dir=False),
        _rect(20, 20, depth=2, name="small-folder", is_dir=True),
        _rect(2, 2, depth=3, name="tiny", is_dir=False),
    ]

    metrics = renderer.draw(rects)

    assert metrics.total_nodes_considered == 4
    assert metrics.rectangles_drawn == 3
    assert metrics.labels_drawn == 2
    assert metrics.nodes_skipped_due_to_area == 1
    assert metrics.folder_containers_suppressed >= 1
    assert len(renderer.state.item_to_rect) == 3


def _rect(w: float, h: float, depth: int, name: str = "node", is_dir: bool = False) -> Rect:
    node = Node(name=name, path=f"C:\\{name}", is_dir=is_dir)
    return Rect(node=node, x=0, y=0, w=w, h=h, depth=depth, fill="#123456")

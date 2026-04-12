from __future__ import annotations

from models import Node, Rect
from colors import color_for_node


PADDING = 2.0
HEADER = 18.0


def compute_treemap(node: Node, x: float, y: float, w: float, h: float, depth: int = 0) -> list[Rect]:
    rects: list[Rect] = []
    if w <= 1 or h <= 1:
        return rects

    rects.append(Rect(node=node, x=x, y=y, w=w, h=h, depth=depth, fill=color_for_node(node)))
    if not node.is_dir or not node.children:
        return rects

    children = [child for child in node.children if child.size > 0]
    if not children:
        return rects

    inner_x = x + PADDING
    inner_y = y + min(HEADER, max(0.0, h * 0.12))
    inner_w = max(0.0, w - 2 * PADDING)
    inner_h = max(0.0, h - (inner_y - y) - PADDING)
    if inner_w <= 1 or inner_h <= 1:
        return rects

    total = sum(child.size for child in children)
    if total <= 0:
        return rects

    horizontal = inner_w >= inner_h
    cursor_x = inner_x
    cursor_y = inner_y

    for index, child in enumerate(children):
        share = child.size / total
        if horizontal:
            remaining = inner_x + inner_w - cursor_x
            child_w = remaining if index == len(children) - 1 else inner_w * share
            child_h = inner_h
            rects.extend(compute_treemap(child, cursor_x, cursor_y, child_w, child_h, depth + 1))
            cursor_x += child_w
        else:
            remaining = inner_y + inner_h - cursor_y
            child_h = remaining if index == len(children) - 1 else inner_h * share
            child_w = inner_w
            rects.extend(compute_treemap(child, cursor_x, cursor_y, child_w, child_h, depth + 1))
            cursor_y += child_h

    return rects

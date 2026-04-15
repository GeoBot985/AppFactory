from __future__ import annotations

from typing import Iterable

from .models import Point


def snap_point(point: tuple[float, float] | tuple[int, int]) -> Point:
    return int(round(point[0])), int(round(point[1]))


def snap_points(points: Iterable[tuple[float, float] | tuple[int, int]]) -> list[Point]:
    return [snap_point(point) for point in points]

from __future__ import annotations

import cv2
import numpy as np

from .models import Connector, ConnectorRoute, Element, GraphEdge, GraphVertex, Node, OrthoSegment


SHAPE_COLOR = (0, 0, 0)
CONNECTOR_COLOR = (0, 0, 0)
UNKNOWN_COLOR = (64, 64, 64)


def render_elements(image_width: int, image_height: int, elements: list[Element]) -> np.ndarray:
    canvas = np.full((image_height, image_width, 3), 255, dtype=np.uint8)

    for element in elements:
        interpreted = element.interpreted_geometry
        points = interpreted.render_points or element.raw_geometry.outline_points or element.raw_geometry.path_points
        if not points:
            continue

        points_array = np.array(points, dtype=np.int32).reshape(-1, 1, 2)
        if element.element_type == "shape_candidate":
            if interpreted.shape_type == "ellipse-like" and len(points) >= 5:
                ellipse = cv2.fitEllipse(points_array)
                cv2.ellipse(canvas, ellipse, SHAPE_COLOR, 2)
            else:
                cv2.polylines(canvas, [points_array], True, SHAPE_COLOR, 2)
        elif element.element_type == "connector_candidate":
            cv2.polylines(canvas, [points_array], interpreted.closed, CONNECTOR_COLOR, 2)
        else:
            cv2.polylines(canvas, [points_array], interpreted.closed, UNKNOWN_COLOR, 1)

    return canvas


def render_structure(image_width: int, image_height: int, nodes: list[Node], connectors: list[Connector]) -> np.ndarray:
    canvas = np.full((image_height, image_width, 3), 255, dtype=np.uint8)
    for node in nodes:
        x, y, w, h = node.bbox
        cv2.rectangle(canvas, (x, y), (x + w, y + h), SHAPE_COLOR, 2)
    for connector in connectors:
        if len(connector.points) < 2:
            continue
        points = np.array(connector.points, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(canvas, [points], False, CONNECTOR_COLOR, 2)
    return canvas


def overlay_interpretation(image: np.ndarray, elements: list[Element]) -> np.ndarray:
    overlay = image.copy()
    for element in elements:
        points = element.interpreted_geometry.render_points or element.raw_geometry.outline_points or element.raw_geometry.path_points
        if not points:
            continue

        color = SHAPE_COLOR
        if element.element_type == "connector_candidate":
            color = (0, 128, 255)
        elif element.element_type == "unknown_candidate":
            color = UNKNOWN_COLOR

        points_array = np.array(points, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(overlay, [points_array], element.interpreted_geometry.closed, color, 2)
        cv2.rectangle(
            overlay,
            (element.bbox[0], element.bbox[1]),
            (element.bbox[0] + element.bbox[2], element.bbox[1] + element.bbox[3]),
            (0, 200, 0),
            1,
        )
    return overlay


def overlay_nodes(image: np.ndarray, nodes: list[Node]) -> np.ndarray:
    overlay = image.copy()
    for node in nodes:
        x, y, w, h = node.bbox
        cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 200, 0), 2)
    return overlay


def overlay_gates(image: np.ndarray, nodes: list[Node]) -> np.ndarray:
    overlay = image.copy()
    for node in nodes:
        ex, ey, ew, eh = node.expanded_bbox
        cv2.rectangle(overlay, (ex, ey), (ex + ew, ey + eh), (180, 180, 0), 1)
        for side, point in node.gates.items():
            cv2.circle(overlay, point, 3, (0, 0, 255), thickness=cv2.FILLED)
            segment = node.gate_segments[side]
            cv2.line(overlay, segment[0], segment[1], (255, 0, 0), 2)
    return overlay


def overlay_segments(image: np.ndarray, segments: list[OrthoSegment], color: tuple[int, int, int]) -> np.ndarray:
    overlay = image.copy()
    for segment in segments:
        cv2.line(overlay, (segment.x1, segment.y1), (segment.x2, segment.y2), color, 2)
    return overlay


def overlay_vertices(image: np.ndarray, vertices: list[GraphVertex]) -> np.ndarray:
    overlay = image.copy()
    color_by_kind = {
        "endpoint": (0, 0, 255),
        "bend": (255, 128, 0),
        "junction": (0, 255, 255),
        "crossing": (255, 0, 255),
        "gate_attach": (0, 255, 0),
    }
    for vertex in vertices:
        cv2.circle(overlay, (vertex.x, vertex.y), 3, color_by_kind.get(vertex.kind, (64, 64, 64)), thickness=cv2.FILLED)
    return overlay


def overlay_graph(image: np.ndarray, vertices: list[GraphVertex], edges: list[GraphEdge]) -> np.ndarray:
    overlay = image.copy()
    vertex_lookup = {vertex.id: (vertex.x, vertex.y) for vertex in vertices}
    for edge in edges:
        cv2.line(overlay, vertex_lookup[edge.v_start], vertex_lookup[edge.v_end], (255, 255, 0), 2)
    return overlay_vertices(overlay, vertices)


def render_graph_structure(image_width: int, image_height: int, nodes: list[Node], routes: list[ConnectorRoute]) -> np.ndarray:
    canvas = np.full((image_height, image_width, 3), 255, dtype=np.uint8)
    for node in nodes:
        x, y, w, h = node.bbox
        cv2.rectangle(canvas, (x, y), (x + w, y + h), SHAPE_COLOR, 2)
    for route in routes:
        if len(route.points) < 2:
            continue
        points = np.array(route.points, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(canvas, [points], False, CONNECTOR_COLOR, 2)
        for point in route.points[1:-1]:
            cv2.circle(canvas, point, 2, CONNECTOR_COLOR, thickness=cv2.FILLED)
    return canvas

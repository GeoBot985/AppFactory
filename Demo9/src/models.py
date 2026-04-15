from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


Point = tuple[int, int]


@dataclass
class RawGeometry:
    outline_points: list[Point] = field(default_factory=list)
    path_points: list[Point] = field(default_factory=list)
    contour_area: int = 0
    perimeter: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InterpretedGeometry:
    shape_type: str | None = None
    path_type: str | None = None
    render_points: list[Point] = field(default_factory=list)
    closed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Element:
    id: str
    element_type: str
    raw_geometry: RawGeometry
    interpreted_geometry: InterpretedGeometry
    bbox: tuple[int, int, int, int]
    center: Point
    confidence: float | None = None
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["raw_geometry"] = self.raw_geometry.to_dict()
        data["interpreted_geometry"] = self.interpreted_geometry.to_dict()
        return data


@dataclass
class Node:
    id: str
    bbox: tuple[int, int, int, int]
    center: Point
    side_midpoints: dict[str, Point]
    expanded_bbox: tuple[int, int, int, int]
    label_region: tuple[int, int, int, int] | None = None
    gates: dict[str, Point] = field(default_factory=dict)
    gate_segments: dict[str, list[Point]] = field(default_factory=dict)
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Connector:
    id: str
    points: list[Point]
    src_node_id: str | None
    src_side: str | None
    dst_node_id: str | None
    dst_side: str | None
    confidence: float
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OrthoSegment:
    id: str
    orientation: str
    x1: int
    y1: int
    x2: int
    y2: int
    component_id: str
    source_count: int = 1
    collapsed_from_ids: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GraphVertex:
    id: str
    kind: str
    x: int
    y: int
    degree: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GraphEdge:
    id: str
    v_start: str
    v_end: str
    orientation: str
    length: float
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConnectorRoute:
    id: str
    src_node_id: str
    src_side: str
    dst_node_id: str
    dst_side: str
    vertex_path: list[str]
    points: list[Point]
    confidence: float
    ambiguous: bool = False
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GraphDiagnostics:
    vertex_count: int
    edge_count: int
    reduced_degree2_vertices: int
    pruned_spurs: int
    collapsed_corridor_groups: int
    status: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Verification:
    edge_overlap_score: float
    pixel_difference_score: float
    status: str
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiagramDocument:
    schema_version: str
    diagram_id: str
    source_file: str
    image_width: int
    image_height: int
    metadata: dict[str, Any]
    processing_parameters: dict[str, Any]
    separation_summary: dict[str, Any]
    elements: list[Element]
    nodes: list[Node]
    connectors: list[Connector]
    routes: list[ConnectorRoute]
    graph: dict[str, Any]
    verification: Verification

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "diagram_id": self.diagram_id,
            "source_file": self.source_file,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "metadata": self.metadata,
            "processing_parameters": self.processing_parameters,
            "separation_summary": self.separation_summary,
            "elements": [element.to_dict() for element in self.elements],
            "nodes": [node.to_dict() for node in self.nodes],
            "connectors": [connector.to_dict() for connector in self.connectors],
            "routes": [route.to_dict() for route in self.routes],
            "graph": self.graph,
            "verification": self.verification.to_dict(),
        }


@dataclass
class ProcessingSummary:
    image_name: str
    element_count: int
    contour_count: int
    connector_count: int
    verification_status: str

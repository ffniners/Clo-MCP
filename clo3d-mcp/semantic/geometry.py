"""
Geometry resolver — classifies pattern edges by geometric properties.

Works via PatternJSON round-trip:
1. After creating a pattern, export PatternJSON from CLO
2. Parse it to extract each line's start/end points
3. Classify lines as top/bottom/left/right/curved/longest/shortest
4. Store mapping {pattern_index: {edge_label: line_index}} in state

Edge classification rules:
  - top:      edge with the highest average Y coordinate
  - bottom:   edge with the lowest average Y coordinate
  - left:     edge with the lowest average X coordinate
  - right:    edge with the highest average X coordinate
  - curved:   any edge containing bezier/curve points (curvature != 0)
  - longest:  edge with the greatest arc length
  - shortest: edge with the smallest arc length

For multi-segment edges (top_left, top_right, etc.), see classify_edges_extended().

V3 additions:
  - extract_edge_geometry(): produce serializable geometry dict for state storage
  - reclassify support via classify_edges_extended + extract_edge_geometry
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Point:
    """A 2D point with optional curvature flag."""
    x: float
    y: float
    curvature: int = 0  # 0=straight, 2=curve, 3=bezier


@dataclass
class Edge:
    """A pattern edge (line) defined by its ordered points."""
    line_index: int
    points: list[Point]

    @property
    def start(self) -> Point:
        return self.points[0]

    @property
    def end(self) -> Point:
        return self.points[-1]

    @property
    def avg_x(self) -> float:
        return sum(p.x for p in self.points) / len(self.points)

    @property
    def avg_y(self) -> float:
        return sum(p.y for p in self.points) / len(self.points)

    @property
    def mid_x(self) -> float:
        return (self.start.x + self.end.x) / 2.0

    @property
    def mid_y(self) -> float:
        return (self.start.y + self.end.y) / 2.0

    @property
    def is_curved(self) -> bool:
        return any(p.curvature != 0 for p in self.points)

    @property
    def arc_length(self) -> float:
        """Sum of Euclidean distances between consecutive points."""
        total = 0.0
        for i in range(len(self.points) - 1):
            dx = self.points[i + 1].x - self.points[i].x
            dy = self.points[i + 1].y - self.points[i].y
            total += math.sqrt(dx * dx + dy * dy)
        return total

    @property
    def is_mostly_horizontal(self) -> bool:
        """True if the edge spans more in X than Y."""
        dx = abs(self.end.x - self.start.x)
        dy = abs(self.end.y - self.start.y)
        return dx > dy

    @property
    def is_mostly_vertical(self) -> bool:
        """True if the edge spans more in Y than X."""
        dx = abs(self.end.x - self.start.x)
        dy = abs(self.end.y - self.start.y)
        return dy > dx


@dataclass
class EdgeClassification:
    """Result of classifying a pattern's edges."""
    labels: dict[str, int]          # edge_label -> line_index
    warnings: list[str] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


def parse_points(raw_points: list[list[float] | tuple]) -> list[Point]:
    """Parse raw [x, y, curvature] lists into Point objects."""
    return [Point(x=float(p[0]), y=float(p[1]), curvature=int(p[2])) for p in raw_points]


def build_edges_from_creation_points(points: list[Point]) -> list[Edge]:
    """
    Build Edge objects from the points used in CreatePatternWithPoints.

    CLO creates edges as consecutive pairs: point[0]→point[1] = line 0,
    point[1]→point[2] = line 1, ..., point[N-1]→point[0] = line N-1.

    Each edge has exactly 2 points (start and end) for straight lines.
    For curves/bezier, intermediate control points belong to the same edge.
    This function builds simple 2-point edges for the straight-line case.
    """
    n = len(points)
    edges = []
    for i in range(n):
        start = points[i]
        end = points[(i + 1) % n]
        edges.append(Edge(line_index=i, points=[start, end]))
    return edges


def build_edges_from_pattern_json(pattern_data: dict) -> list[Edge]:
    """
    Build Edge objects from CLO's ExportPatternJSON output for a single pattern.

    Expected structure (per pattern in the JSON):
    {
        "PatternOutlines": [
            {
                "Lines": [
                    {
                        "Points": [
                            {"X": 0.0, "Y": 0.0, "Curvature": 0},
                            ...
                        ]
                    },
                    ...
                ]
            }
        ]
    }

    Falls back to simpler structures if the exact format differs.
    """
    edges = []
    outlines = pattern_data.get("PatternOutlines", [])
    if not outlines:
        # Try alternative key names
        outlines = pattern_data.get("Outlines", [])

    for outline in outlines:
        lines = outline.get("Lines", outline.get("lines", []))
        for line_idx, line_data in enumerate(lines):
            raw_points = line_data.get("Points", line_data.get("points", []))
            points = []
            for rp in raw_points:
                if isinstance(rp, dict):
                    x = float(rp.get("X", rp.get("x", 0)))
                    y = float(rp.get("Y", rp.get("y", 0)))
                    c = int(rp.get("Curvature", rp.get("curvature", 0)))
                    points.append(Point(x=x, y=y, curvature=c))
                elif isinstance(rp, (list, tuple)):
                    points.append(Point(x=float(rp[0]), y=float(rp[1]),
                                        curvature=int(rp[2]) if len(rp) > 2 else 0))
            if points:
                edges.append(Edge(line_index=len(edges), points=points))

    return edges


def classify_edges(edges: list[Edge]) -> EdgeClassification:
    """
    Classify edges into semantic labels: top, bottom, left, right,
    curved, longest, shortest.

    Handles ambiguous cases by falling back to index order and flagging
    a warning.

    Returns an EdgeClassification with labels and any warnings.
    """
    if not edges:
        return EdgeClassification(labels={}, warnings=["No edges to classify"])

    warnings: list[str] = []
    labels: dict[str, int] = {}

    # --- Positional classification ---
    # Sort by avg_y descending → highest = top
    by_avg_y_desc = sorted(edges, key=lambda e: e.avg_y, reverse=True)
    top_edge = by_avg_y_desc[0]
    labels["top"] = top_edge.line_index
    if (len(by_avg_y_desc) > 1
            and abs(by_avg_y_desc[0].avg_y - by_avg_y_desc[1].avg_y) < 1e-3):
        warnings.append(
            f"Ambiguous 'top': lines {by_avg_y_desc[0].line_index} and "
            f"{by_avg_y_desc[1].line_index} have nearly identical avg Y. "
            f"Using line {top_edge.line_index} (lower index)."
        )

    # lowest avg_y = bottom
    by_avg_y_asc = sorted(edges, key=lambda e: e.avg_y)
    bottom_edge = by_avg_y_asc[0]
    labels["bottom"] = bottom_edge.line_index
    if (len(by_avg_y_asc) > 1
            and abs(by_avg_y_asc[0].avg_y - by_avg_y_asc[1].avg_y) < 1e-3):
        warnings.append(
            f"Ambiguous 'bottom': lines {by_avg_y_asc[0].line_index} and "
            f"{by_avg_y_asc[1].line_index} have nearly identical avg Y. "
            f"Using line {bottom_edge.line_index} (lower index)."
        )

    # lowest avg_x = left
    by_avg_x_asc = sorted(edges, key=lambda e: e.avg_x)
    left_edge = by_avg_x_asc[0]
    labels["left"] = left_edge.line_index
    if (len(by_avg_x_asc) > 1
            and abs(by_avg_x_asc[0].avg_x - by_avg_x_asc[1].avg_x) < 1e-3):
        warnings.append(
            f"Ambiguous 'left': lines {by_avg_x_asc[0].line_index} and "
            f"{by_avg_x_asc[1].line_index} have nearly identical avg X. "
            f"Using line {left_edge.line_index} (lower index)."
        )

    # highest avg_x = right
    by_avg_x_desc = sorted(edges, key=lambda e: e.avg_x, reverse=True)
    right_edge = by_avg_x_desc[0]
    labels["right"] = right_edge.line_index
    if (len(by_avg_x_desc) > 1
            and abs(by_avg_x_desc[0].avg_x - by_avg_x_desc[1].avg_x) < 1e-3):
        warnings.append(
            f"Ambiguous 'right': lines {by_avg_x_desc[0].line_index} and "
            f"{by_avg_x_desc[1].line_index} have nearly identical avg X. "
            f"Using line {right_edge.line_index} (lower index)."
        )

    # --- Curved edges ---
    curved_edges = [e for e in edges if e.is_curved]
    if curved_edges:
        labels["curved"] = curved_edges[0].line_index
        if len(curved_edges) > 1:
            for i, ce in enumerate(curved_edges):
                labels[f"curved_{i}"] = ce.line_index

    # --- Length classification ---
    by_length_desc = sorted(edges, key=lambda e: e.arc_length, reverse=True)
    labels["longest"] = by_length_desc[0].line_index
    if (len(by_length_desc) > 1
            and abs(by_length_desc[0].arc_length - by_length_desc[1].arc_length) < 1e-3):
        warnings.append(
            f"Ambiguous 'longest': lines {by_length_desc[0].line_index} and "
            f"{by_length_desc[1].line_index} have nearly identical length. "
            f"Using line {by_length_desc[0].line_index} (lower index)."
        )

    by_length_asc = sorted(edges, key=lambda e: e.arc_length)
    labels["shortest"] = by_length_asc[0].line_index
    if (len(by_length_asc) > 1
            and abs(by_length_asc[0].arc_length - by_length_asc[1].arc_length) < 1e-3):
        warnings.append(
            f"Ambiguous 'shortest': lines {by_length_asc[0].line_index} and "
            f"{by_length_asc[1].line_index} have nearly identical length. "
            f"Using line {by_length_asc[0].line_index} (lower index)."
        )

    return EdgeClassification(labels=labels, warnings=warnings, edges=edges)


def classify_edges_extended(edges: list[Edge]) -> EdgeClassification:
    """
    Extended classification that adds compound labels useful for garments:
      top_left, top_right, bottom_left, bottom_right

    These are assigned by splitting horizontal edges at the midpoint
    of the pattern's bounding box, or by identifying which vertical
    edges are on which side of horizontal ones.

    This extends the base classify_edges() result.
    """
    result = classify_edges(edges)
    if len(edges) < 4:
        return result

    # Compute bounding box center
    all_x = [p.x for e in edges for p in e.points]
    all_y = [p.y for e in edges for p in e.points]
    cx = (min(all_x) + max(all_x)) / 2.0
    cy = (min(all_y) + max(all_y)) / 2.0

    # Find top-region edges (above center Y) sorted by X
    top_edges = sorted(
        [e for e in edges if e.avg_y > cy],
        key=lambda e: e.avg_x,
    )
    if len(top_edges) >= 2:
        result.labels["top_left"] = top_edges[0].line_index
        result.labels["top_right"] = top_edges[-1].line_index
    elif len(top_edges) == 1:
        # Single top edge — assign it to both (caller can check)
        result.labels["top_left"] = top_edges[0].line_index
        result.labels["top_right"] = top_edges[0].line_index

    # Bottom-region edges (below center Y) sorted by X
    bottom_edges = sorted(
        [e for e in edges if e.avg_y < cy],
        key=lambda e: e.avg_x,
    )
    if len(bottom_edges) >= 2:
        result.labels["bottom_left"] = bottom_edges[0].line_index
        result.labels["bottom_right"] = bottom_edges[-1].line_index
    elif len(bottom_edges) == 1:
        result.labels["bottom_left"] = bottom_edges[0].line_index
        result.labels["bottom_right"] = bottom_edges[0].line_index

    # Edges exactly at center Y get a warning
    center_edges = [e for e in edges if abs(e.avg_y - cy) < 1e-3]
    if center_edges:
        result.warnings.append(
            f"Edges at vertical center (ambiguous top/bottom): "
            f"{[e.line_index for e in center_edges]}"
        )

    return result


def get_edge_length(edges: list[Edge], label: str,
                    labels: dict[str, int]) -> float | None:
    """Get the arc length of an edge by its label. Returns None if not found."""
    idx = labels.get(label)
    if idx is None:
        return None
    for e in edges:
        if e.line_index == idx:
            return e.arc_length
    return None


def extract_edge_geometry(edges: list[Edge], labels: dict[str, int]) -> dict:
    """
    Extract serializable geometry data from classified edges.

    Returns a dict of {edge_label: {line_index, arc_length, is_curved, points}}
    suitable for storing in state and using for downstream seam length checks.
    """
    geometry: dict[str, dict] = {}
    # Build line_index → edge lookup
    edge_by_idx = {e.line_index: e for e in edges}

    for label, line_idx in labels.items():
        edge = edge_by_idx.get(line_idx)
        if edge is None:
            continue
        geometry[label] = {
            "line_index": line_idx,
            "arc_length": round(edge.arc_length, 4),
            "is_curved": edge.is_curved,
            "points": [[p.x, p.y, p.curvature] for p in edge.points],
        }
    return geometry

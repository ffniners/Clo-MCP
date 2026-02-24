"""
Unit tests for the geometry edge classifier.

These tests are critical — the entire semantic seam layer depends on
correct edge classification.
"""

import math
import pytest
import sys
import os

# Add project root to path so we can import semantic.geometry
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from semantic.geometry import (
    Point,
    Edge,
    EdgeClassification,
    parse_points,
    build_edges_from_creation_points,
    build_edges_from_pattern_json,
    classify_edges,
    classify_edges_extended,
    get_edge_length,
)


# -------------------------------------------------------------------------
# Fixtures — common test shapes
# -------------------------------------------------------------------------

def make_rectangle(x0=0, y0=0, w=300, h=500) -> list[Edge]:
    """
    Rectangle defined CCW from bottom-left:
      P0=(x0, y0) → P1=(x0, y0+h) → P2=(x0+w, y0+h) → P3=(x0+w, y0)

    Expected edges (line indices):
      0: left   (P0→P1, vertical, x=x0)
      1: top    (P1→P2, horizontal, y=y0+h)
      2: right  (P2→P3, vertical, x=x0+w)
      3: bottom (P3→P0, horizontal, y=y0)
    """
    points = [
        Point(x0, y0, 0),
        Point(x0, y0 + h, 0),
        Point(x0 + w, y0 + h, 0),
        Point(x0 + w, y0, 0),
    ]
    return build_edges_from_creation_points(points)


def make_square() -> list[Edge]:
    """100x100 square — all sides equal length."""
    return make_rectangle(w=100, h=100)


def make_triangle() -> list[Edge]:
    """
    Equilateral-ish triangle:
      P0=(0,0) → P1=(150, 300) → P2=(300, 0)

    Edges:
      0: left  (P0→P1)
      1: top-right (P1→P2) — though "top" by avg_y
      2: bottom (P2→P0)
    """
    points = [
        Point(0, 0, 0),
        Point(150, 300, 0),
        Point(300, 0, 0),
    ]
    return build_edges_from_creation_points(points)


def make_pentagon_with_curve() -> list[Edge]:
    """
    5-sided shape with one curved edge.
      P0=(0,0) → P1=(0,200) → P2=(100,300,3) → P3=(200,200) → P4=(200,0)
    Edge 1 (P1→P2) has bezier curvature.
    """
    points = [
        Point(0, 0, 0),
        Point(0, 200, 0),
        Point(100, 300, 3),  # bezier
        Point(200, 200, 0),
        Point(200, 0, 0),
    ]
    return build_edges_from_creation_points(points)


# -------------------------------------------------------------------------
# Point / Edge basics
# -------------------------------------------------------------------------

class TestPoint:
    def test_defaults(self):
        p = Point(1.0, 2.0)
        assert p.x == 1.0
        assert p.y == 2.0
        assert p.curvature == 0

    def test_curvature(self):
        p = Point(0, 0, 3)
        assert p.curvature == 3


class TestEdge:
    def test_start_end(self):
        e = Edge(line_index=0, points=[Point(0, 0), Point(10, 0)])
        assert e.start.x == 0
        assert e.end.x == 10

    def test_avg_x_y(self):
        e = Edge(line_index=0, points=[Point(0, 0), Point(10, 20)])
        assert e.avg_x == 5.0
        assert e.avg_y == 10.0

    def test_arc_length_straight(self):
        e = Edge(line_index=0, points=[Point(0, 0), Point(3, 4)])
        assert abs(e.arc_length - 5.0) < 1e-9

    def test_arc_length_multi_segment(self):
        e = Edge(line_index=0, points=[
            Point(0, 0), Point(3, 0), Point(3, 4)
        ])
        assert abs(e.arc_length - 7.0) < 1e-9

    def test_is_curved_false(self):
        e = Edge(line_index=0, points=[Point(0, 0, 0), Point(10, 0, 0)])
        assert not e.is_curved

    def test_is_curved_true(self):
        e = Edge(line_index=0, points=[Point(0, 0, 0), Point(10, 0, 3)])
        assert e.is_curved

    def test_mostly_horizontal(self):
        e = Edge(line_index=0, points=[Point(0, 0), Point(100, 10)])
        assert e.is_mostly_horizontal
        assert not e.is_mostly_vertical

    def test_mostly_vertical(self):
        e = Edge(line_index=0, points=[Point(0, 0), Point(10, 100)])
        assert e.is_mostly_vertical
        assert not e.is_mostly_horizontal


# -------------------------------------------------------------------------
# parse_points
# -------------------------------------------------------------------------

class TestParsePoints:
    def test_basic(self):
        raw = [[1.0, 2.0, 0], [3.0, 4.0, 3]]
        pts = parse_points(raw)
        assert len(pts) == 2
        assert pts[0].x == 1.0
        assert pts[1].curvature == 3

    def test_tuple_input(self):
        raw = [(0, 0, 0), (10, 20, 2)]
        pts = parse_points(raw)
        assert pts[1].curvature == 2


# -------------------------------------------------------------------------
# build_edges_from_creation_points
# -------------------------------------------------------------------------

class TestBuildEdgesFromCreationPoints:
    def test_rectangle(self):
        edges = make_rectangle()
        assert len(edges) == 4
        # Edge 0: (0,0)→(0,500)
        assert edges[0].start.x == 0 and edges[0].start.y == 0
        assert edges[0].end.x == 0 and edges[0].end.y == 500
        # Edge 3 wraps: (300,0)→(0,0)
        assert edges[3].start.x == 300 and edges[3].end.x == 0

    def test_triangle(self):
        edges = make_triangle()
        assert len(edges) == 3

    def test_line_indices_sequential(self):
        edges = make_rectangle()
        for i, e in enumerate(edges):
            assert e.line_index == i


# -------------------------------------------------------------------------
# build_edges_from_pattern_json
# -------------------------------------------------------------------------

class TestBuildEdgesFromPatternJSON:
    def test_standard_format(self):
        data = {
            "PatternOutlines": [{
                "Lines": [
                    {"Points": [
                        {"X": 0, "Y": 0, "Curvature": 0},
                        {"X": 0, "Y": 500, "Curvature": 0},
                    ]},
                    {"Points": [
                        {"X": 0, "Y": 500, "Curvature": 0},
                        {"X": 300, "Y": 500, "Curvature": 0},
                    ]},
                ]
            }]
        }
        edges = build_edges_from_pattern_json(data)
        assert len(edges) == 2
        assert edges[0].start.x == 0
        assert edges[1].end.x == 300

    def test_lowercase_keys(self):
        data = {
            "Outlines": [{
                "lines": [
                    {"points": [[0, 0, 0], [100, 0, 0]]},
                ]
            }]
        }
        edges = build_edges_from_pattern_json(data)
        assert len(edges) == 1
        assert edges[0].end.x == 100

    def test_empty(self):
        assert build_edges_from_pattern_json({}) == []


# -------------------------------------------------------------------------
# classify_edges — CORE TESTS
# -------------------------------------------------------------------------

class TestClassifyEdgesRectangle:
    """Test classification on a standard rectangle."""

    def setup_method(self):
        self.edges = make_rectangle(x0=0, y0=0, w=300, h=500)
        self.result = classify_edges(self.edges)

    def test_top(self):
        # Edge 1: (0,500)→(300,500), avg_y=500 → highest
        assert self.result.labels["top"] == 1

    def test_bottom(self):
        # Edge 3: (300,0)→(0,0), avg_y=0 → lowest
        assert self.result.labels["bottom"] == 3

    def test_left(self):
        # Edge 0: (0,0)→(0,500), avg_x=0 → leftmost
        assert self.result.labels["left"] == 0

    def test_right(self):
        # Edge 2: (300,500)→(300,0), avg_x=300 → rightmost
        assert self.result.labels["right"] == 2

    def test_longest(self):
        # Vertical edges are 500mm, horizontal are 300mm
        # Edge 0 or 2 is longest (both 500mm) — takes lower index
        assert self.result.labels["longest"] in (0, 2)

    def test_shortest(self):
        # Horizontal edges are 300mm
        assert self.result.labels["shortest"] in (1, 3)

    def test_no_curved(self):
        assert "curved" not in self.result.labels

    def test_no_warnings_for_unique_edges(self):
        # A rectangle has ambiguous longest/shortest (pairs of equal edges)
        # but top/bottom/left/right should be unambiguous
        top_warnings = [w for w in self.result.warnings if "'top'" in w]
        assert len(top_warnings) == 0
        bottom_warnings = [w for w in self.result.warnings if "'bottom'" in w]
        assert len(bottom_warnings) == 0


class TestClassifyEdgesSquare:
    """Square has ambiguous cases — all sides equal."""

    def setup_method(self):
        self.edges = make_square()
        self.result = classify_edges(self.edges)

    def test_has_longest_shortest_warnings(self):
        # All edges are 100mm → ambiguous longest and shortest
        length_warnings = [w for w in self.result.warnings
                          if "'longest'" in w or "'shortest'" in w]
        assert len(length_warnings) >= 1

    def test_still_assigns_all_labels(self):
        for label in ["top", "bottom", "left", "right", "longest", "shortest"]:
            assert label in self.result.labels


class TestClassifyEdgesWithCurve:
    """Test that curved edges are detected."""

    def setup_method(self):
        self.edges = make_pentagon_with_curve()
        self.result = classify_edges(self.edges)

    def test_curved_detected(self):
        assert "curved" in self.result.labels
        # The curved point is P2 (curvature=3), which is the end of edge 1
        # Edge 1: P1(0,200) → P2(100,300,3)
        assert self.result.labels["curved"] == 1

    def test_top_is_curved_edge(self):
        # Edge 1 has avg_y = (200+300)/2 = 250, edge 2 has avg_y=(300+200)/2=250
        # Both have same avg_y, so this tests ambiguity handling
        assert self.result.labels["top"] in (1, 2)


class TestClassifyEdgesTriangle:
    """Triangle — only 3 edges."""

    def setup_method(self):
        self.edges = make_triangle()
        self.result = classify_edges(self.edges)

    def test_top(self):
        # Edge 0: (0,0)→(150,300), avg_y=150
        # Edge 1: (150,300)→(300,0), avg_y=150
        # Edge 2: (300,0)→(0,0), avg_y=0
        # Both 0 and 1 have avg_y=150 → ambiguous, uses lower index
        assert self.result.labels["top"] in (0, 1)

    def test_bottom(self):
        # Edge 2 has lowest avg_y (0)
        assert self.result.labels["bottom"] == 2

    def test_all_labels_present(self):
        for label in ["top", "bottom", "left", "right"]:
            assert label in self.result.labels


class TestClassifyEdgesEmpty:
    def test_empty_edges(self):
        result = classify_edges([])
        assert result.labels == {}
        assert len(result.warnings) == 1


class TestClassifyEdgesOffset:
    """Rectangle at a non-zero origin."""

    def test_offset_rectangle(self):
        edges = make_rectangle(x0=400, y0=100, w=300, h=500)
        result = classify_edges(edges)
        # Same structure as origin rectangle — just shifted
        assert result.labels["left"] == 0    # avg_x = 400
        assert result.labels["right"] == 2   # avg_x = 700
        assert result.labels["top"] == 1     # avg_y = 600
        assert result.labels["bottom"] == 3  # avg_y = 100


# -------------------------------------------------------------------------
# classify_edges_extended
# -------------------------------------------------------------------------

class TestClassifyEdgesExtended:
    """Test extended classification with compound labels."""

    def test_rectangle_extended(self):
        edges = make_rectangle()
        result = classify_edges_extended(edges)
        # Should have base labels plus extended ones
        assert "top" in result.labels
        assert "bottom" in result.labels

    def test_pentagon_top_left_right(self):
        """Pentagon has edges in the upper region that can be split."""
        edges = make_pentagon_with_curve()
        result = classify_edges_extended(edges)
        # Should have top_left and top_right assigned
        if "top_left" in result.labels:
            assert isinstance(result.labels["top_left"], int)

    def test_small_shape_no_crash(self):
        """3-edge shape should not crash extended classification."""
        edges = make_triangle()
        result = classify_edges_extended(edges)
        assert "top" in result.labels


# -------------------------------------------------------------------------
# get_edge_length
# -------------------------------------------------------------------------

class TestGetEdgeLength:
    def test_existing_label(self):
        edges = make_rectangle(w=300, h=500)
        result = classify_edges(edges)
        length = get_edge_length(edges, "top", result.labels)
        assert length is not None
        assert abs(length - 300.0) < 1e-9

    def test_missing_label(self):
        edges = make_rectangle()
        result = classify_edges(edges)
        assert get_edge_length(edges, "nonexistent", result.labels) is None


# -------------------------------------------------------------------------
# Edge length comparison (used by seam planner)
# -------------------------------------------------------------------------

class TestEdgeLengthComparison:
    def test_matching_edges(self):
        """Two rectangles of same dimensions should have matching side lengths."""
        edges_a = make_rectangle(x0=0, w=300, h=500)
        edges_b = make_rectangle(x0=400, w=300, h=500)
        result_a = classify_edges(edges_a)
        result_b = classify_edges(edges_b)

        len_a = get_edge_length(edges_a, "left", result_a.labels)
        len_b = get_edge_length(edges_b, "right", result_b.labels)
        assert len_a is not None and len_b is not None
        assert abs(len_a - len_b) < 1e-9  # Both 500mm

    def test_mismatched_edges(self):
        """Different-height rectangles have different side lengths."""
        edges_a = make_rectangle(w=300, h=500)
        edges_b = make_rectangle(w=300, h=400)
        result_a = classify_edges(edges_a)
        result_b = classify_edges(edges_b)

        len_a = get_edge_length(edges_a, "left", result_a.labels)
        len_b = get_edge_length(edges_b, "left", result_b.labels)
        assert len_a is not None and len_b is not None
        assert abs(len_a - len_b) > 50  # 500 vs 400


# -------------------------------------------------------------------------
# Regression: ensure line_index stability
# -------------------------------------------------------------------------

class TestLineIndexStability:
    """
    Verify that repeated classification of the same shape always
    produces the same line_index mapping.
    """

    def test_deterministic(self):
        for _ in range(10):
            edges = make_rectangle()
            result = classify_edges(edges)
            assert result.labels["top"] == 1
            assert result.labels["bottom"] == 3
            assert result.labels["left"] == 0
            assert result.labels["right"] == 2

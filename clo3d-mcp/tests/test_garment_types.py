"""
Tests for garment_types.py — derivation functions, registry, spec loading.
"""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from semantic.garment_types import (
    derive_tshirt_pieces,
    derive_aline_skirt_pieces,
    get_garment_type,
    list_garment_types,
    load_garment_from_spec,
    load_garment_specs_from_dir,
    register_garment_type,
    get_derivation_function,
    GarmentType,
    PieceDefinition,
    SeamDefinition,
    GARMENT_REGISTRY,
    DEFAULT_TSHIRT_MEASUREMENTS,
)


class TestDeriveTshirtPieces:
    def test_returns_four_roles(self):
        pieces = derive_tshirt_pieces({})
        assert set(pieces.keys()) == {"front_bodice", "back_bodice", "sleeve_left", "sleeve_right"}

    def test_front_bodice_has_six_points(self):
        pieces = derive_tshirt_pieces({})
        assert len(pieces["front_bodice"]) == 6

    def test_sleeves_are_rectangles(self):
        pieces = derive_tshirt_pieces({})
        assert len(pieces["sleeve_left"]) == 4
        assert len(pieces["sleeve_right"]) == 4

    def test_custom_measurements_override(self):
        custom = {"chest_width_mm": 600, "body_length_mm": 800}
        pieces = derive_tshirt_pieces(custom)
        front = pieces["front_bodice"]
        # Bottom-right X should be chest_width = 600
        assert front[5][0] == 600.0
        # Top-left Y should be body_length = 800
        assert front[1][1] == 800.0

    def test_neck_bezier_points(self):
        pieces = derive_tshirt_pieces({})
        front = pieces["front_bodice"]
        # Points 2 and 3 should have curvature = 3 (bezier)
        assert front[2][2] == 3
        assert front[3][2] == 3

    def test_back_bodice_offset(self):
        pieces = derive_tshirt_pieces({})
        front_max_x = max(p[0] for p in pieces["front_bodice"])
        back_min_x = min(p[0] for p in pieces["back_bodice"])
        # Back bodice should be offset to the right with a gap
        assert back_min_x > front_max_x

    def test_back_neck_shallower(self):
        pieces = derive_tshirt_pieces({})
        front = pieces["front_bodice"]
        back = pieces["back_bodice"]
        # Front neck drop (P2 Y offset from P1 Y)
        front_neck_y = front[2][1]
        front_shoulder_y = front[1][1]
        front_drop = front_shoulder_y - front_neck_y
        # Back neck drop
        back_neck_y = back[2][1]
        back_shoulder_y = back[1][1]
        back_drop = back_shoulder_y - back_neck_y
        assert back_drop < front_drop


class TestDeriveAlineSkirtPieces:
    def test_returns_two_roles(self):
        pieces = derive_aline_skirt_pieces({})
        assert set(pieces.keys()) == {"front_panel", "back_panel"}

    def test_panels_are_trapezoids(self):
        pieces = derive_aline_skirt_pieces({})
        assert len(pieces["front_panel"]) == 4
        assert len(pieces["back_panel"]) == 4

    def test_hem_wider_than_waist(self):
        pieces = derive_aline_skirt_pieces({})
        front = pieces["front_panel"]
        # Hem width (P3[0] - P0[0]) should be > waist width (P2[0] - P1[0])
        hem_width = front[3][0] - front[0][0]
        waist_width = front[2][0] - front[1][0]
        assert hem_width > waist_width

    def test_custom_measurements(self):
        custom = {"waist_width_mm": 400, "hem_width_mm": 600, "skirt_length_mm": 700}
        pieces = derive_aline_skirt_pieces(custom)
        front = pieces["front_panel"]
        # Waist points should span 400mm
        assert abs((front[2][0] - front[1][0]) - 400.0) < 1e-6


class TestGarmentRegistry:
    def test_tshirt_registered(self):
        assert "t_shirt" in list_garment_types()

    def test_aline_skirt_registered(self):
        assert "a_line_skirt" in list_garment_types()

    def test_get_garment_type(self):
        gt = get_garment_type("t_shirt")
        assert gt is not None
        assert gt.name == "t_shirt"
        assert len(gt.pieces) == 4
        assert len(gt.seam_plan) == 6

    def test_unknown_garment_returns_none(self):
        assert get_garment_type("nonexistent") is None

    def test_get_derivation_function(self):
        fn = get_derivation_function("t_shirt")
        assert fn is not None
        assert callable(fn)

        fn2 = get_derivation_function("a_line_skirt")
        assert fn2 is not None

    def test_register_garment_type(self):
        custom = GarmentType(
            name="test_garment",
            pieces=[PieceDefinition(role="panel", description="Test panel")],
            seam_plan=[],
        )
        register_garment_type(custom)
        assert "test_garment" in list_garment_types()
        assert get_garment_type("test_garment") is not None
        # Clean up
        del GARMENT_REGISTRY["test_garment"]


class TestSpecFileLoading:
    def test_load_from_json(self, tmp_path):
        spec = {
            "name": "test_spec",
            "pieces": [
                {"role": "panel_a", "description": "Panel A"},
                {"role": "panel_b", "description": "Panel B"},
            ],
            "seam_plan": [
                {"pattern_a": "panel_a", "edge_a": "left",
                 "pattern_b": "panel_b", "edge_b": "right",
                 "label": "side_seam", "flip": False},
            ],
            "default_measurements": {"width_mm": 500},
        }
        spec_path = str(tmp_path / "test.json")
        with open(spec_path, "w") as f:
            json.dump(spec, f)

        gt = load_garment_from_spec(spec_path)
        assert gt.name == "test_spec"
        assert len(gt.pieces) == 2
        assert len(gt.seam_plan) == 1
        assert gt.default_measurements["width_mm"] == 500

    def test_load_from_dir(self, tmp_path):
        for name in ["a.json", "b.json"]:
            spec = {"name": name.replace(".json", ""), "pieces": [], "seam_plan": []}
            with open(str(tmp_path / name), "w") as f:
                json.dump(spec, f)

        loaded = load_garment_specs_from_dir(str(tmp_path))
        assert len(loaded) == 2
        names = {gt.name for gt in loaded}
        assert "a" in names
        assert "b" in names

    def test_load_from_nonexistent_dir(self):
        loaded = load_garment_specs_from_dir("/nonexistent/path")
        assert loaded == []

    def test_malformed_spec_skipped(self, tmp_path):
        # Write invalid JSON
        with open(str(tmp_path / "bad.json"), "w") as f:
            f.write("not json")
        # Write valid spec
        spec = {"name": "good", "pieces": [], "seam_plan": []}
        with open(str(tmp_path / "good.json"), "w") as f:
            json.dump(spec, f)

        loaded = load_garment_specs_from_dir(str(tmp_path))
        assert len(loaded) == 1
        assert loaded[0].name == "good"

    def test_sample_spec_file_loads(self):
        """The bundled a_line_skirt.json spec file loads successfully."""
        spec_dir = os.path.join(os.path.dirname(__file__), "..", "garment_specs")
        spec_path = os.path.join(spec_dir, "a_line_skirt.json")
        if os.path.exists(spec_path):
            gt = load_garment_from_spec(spec_path)
            assert gt.name == "a_line_skirt"
            assert len(gt.pieces) == 2
            assert len(gt.seam_plan) == 2

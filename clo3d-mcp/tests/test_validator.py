"""
Tests for semantic/validator.py — garment validation checks.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from semantic.state_manager import StateManager
from semantic.validator import GarmentValidator, ValidationResult


@pytest.fixture
def tmp_state_path(tmp_path):
    path = str(tmp_path / "test_state.json")
    os.environ["CLO_MCP_STATE_PATH"] = path
    yield path
    os.environ.pop("CLO_MCP_STATE_PATH", None)


@pytest.fixture
def state_manager(tmp_state_path):
    return StateManager(bridge_fn=None)


def _build_valid_tshirt_state(sm: StateManager) -> None:
    """Populate state with a valid t-shirt (4 pieces, 6 seams, fabric)."""
    sm.register_pattern(
        index=0, name="Front_Bodice", role="front_bodice",
        edges={"top": 1, "bottom": 5, "left": 0, "right": 4,
               "top_left": 1, "top_right": 3},
        edge_geometry={
            "top_left": {"arc_length": 210.0},
            "top_right": {"arc_length": 210.0},
            "left": {"arc_length": 700.0},
            "right": {"arc_length": 700.0},
        },
    )
    sm.register_pattern(
        index=1, name="Back_Bodice", role="back_bodice",
        edges={"top": 1, "bottom": 5, "left": 0, "right": 4,
               "top_left": 1, "top_right": 3},
        edge_geometry={
            "top_left": {"arc_length": 210.0},
            "top_right": {"arc_length": 210.0},
            "left": {"arc_length": 700.0},
            "right": {"arc_length": 700.0},
        },
    )
    sm.register_pattern(
        index=2, name="Sleeve_Left", role="sleeve_left",
        edges={"top": 1, "bottom": 3, "left": 0, "right": 2},
        edge_geometry={
            "top": {"arc_length": 180.0},
            "bottom": {"arc_length": 180.0},
        },
    )
    sm.register_pattern(
        index=3, name="Sleeve_Right", role="sleeve_right",
        edges={"top": 1, "bottom": 3, "left": 0, "right": 2},
        edge_geometry={
            "top": {"arc_length": 180.0},
            "bottom": {"arc_length": 180.0},
        },
    )

    # Fabric
    sm.register_fabric(index=0, name="cotton", path="/cotton.zfab")
    for i in range(4):
        sm.assign_fabric_to_pattern(0, i)

    # Seams
    sm.register_seam("left_side_seam", "Front_Bodice", "left",
                     "Back_Bodice", "right")
    sm.register_seam("right_side_seam", "Front_Bodice", "right",
                     "Back_Bodice", "left")
    sm.register_seam("left_shoulder_front", "Front_Bodice", "top_left",
                     "Sleeve_Left", "bottom")
    sm.register_seam("right_shoulder_front", "Front_Bodice", "top_right",
                     "Sleeve_Right", "bottom")
    sm.register_seam("left_shoulder_back", "Back_Bodice", "top_left",
                     "Sleeve_Left", "top")
    sm.register_seam("right_shoulder_back", "Back_Bodice", "top_right",
                     "Sleeve_Right", "top")


class TestValidatorEmpty:
    def test_empty_state_no_garment_type(self, state_manager):
        v = GarmentValidator(state_manager)
        result = v.validate()
        assert result.valid is False
        assert any("No patterns" in e for e in result.errors)

    def test_empty_state_with_garment_type(self, state_manager):
        v = GarmentValidator(state_manager)
        result = v.validate("t_shirt")
        assert result.valid is False


class TestValidatorValidState:
    def test_valid_tshirt(self, state_manager):
        _build_valid_tshirt_state(state_manager)
        v = GarmentValidator(state_manager)
        result = v.validate("t_shirt")
        assert result.valid is True
        assert len(result.errors) == 0
        assert "pattern_count" in result.checks_passed
        assert "required_pieces" in result.checks_passed
        assert "seam_completeness" in result.checks_passed
        assert "duplicate_seams" in result.checks_passed

    def test_valid_no_garment_type(self, state_manager):
        _build_valid_tshirt_state(state_manager)
        v = GarmentValidator(state_manager)
        result = v.validate()
        assert result.valid is True
        # Garment-specific checks skipped
        assert "required_pieces" not in result.checks_passed
        assert "seam_completeness" not in result.checks_passed


class TestValidatorPatternCount:
    def test_wrong_count(self, state_manager):
        state_manager.register_pattern(index=0, name="Front", role="front_bodice")
        v = GarmentValidator(state_manager)
        result = v.validate("t_shirt")
        assert result.valid is False
        assert any("Expected 4" in e for e in result.errors)


class TestValidatorRequiredPieces:
    def test_missing_pieces(self, state_manager):
        state_manager.register_pattern(index=0, name="Front", role="front_bodice")
        state_manager.register_pattern(index=1, name="Back", role="back_bodice")
        v = GarmentValidator(state_manager)
        result = v.validate("t_shirt")
        assert any("Missing required pieces" in e for e in result.errors)


class TestValidatorSeamCompleteness:
    def test_missing_seams(self, state_manager):
        _build_valid_tshirt_state(state_manager)
        # Clear seams but keep patterns
        state_manager.clear_seams()
        v = GarmentValidator(state_manager)
        result = v.validate("t_shirt")
        assert result.valid is False
        assert any("Missing seams" in e for e in result.errors)


class TestValidatorDuplicateSeams:
    def test_duplicate_seams(self, state_manager):
        state_manager.register_pattern(index=0, name="A", role="front")
        state_manager.register_pattern(index=1, name="B", role="back")
        state_manager.register_seam("s1", "A", "top", "B", "bottom")
        state_manager.register_seam("s2", "A", "top", "B", "bottom")
        v = GarmentValidator(state_manager)
        result = v.validate()
        assert result.valid is False
        assert any("Duplicate" in e for e in result.errors)


class TestValidatorEdgeLengths:
    def test_length_mismatch_warning(self, state_manager):
        state_manager.register_pattern(
            index=0, name="A",
            edge_geometry={"top": {"arc_length": 100.0}},
            edges={"top": 0},
        )
        state_manager.register_pattern(
            index=1, name="B",
            edge_geometry={"bottom": {"arc_length": 200.0}},
            edges={"bottom": 0},
        )
        state_manager.register_seam("s1", "A", "top", "B", "bottom")
        v = GarmentValidator(state_manager)
        result = v.validate()
        # Length mismatch is a warning, not an error
        assert result.valid is True
        assert any("length" in w.lower() for w in result.warnings)


class TestValidatorFabricAssignment:
    def test_no_fabric_warning(self, state_manager):
        state_manager.register_pattern(index=0, name="A")
        state_manager.register_pattern(index=1, name="B")
        state_manager.register_seam("s1", "A", "top", "B", "bottom")
        v = GarmentValidator(state_manager)
        result = v.validate()
        assert any("fabric" in w.lower() for w in result.warnings)


class TestValidatorOrphanPieces:
    def test_orphan_pieces_warning(self, state_manager):
        state_manager.register_pattern(index=0, name="A")
        state_manager.register_pattern(index=1, name="B")
        state_manager.register_pattern(index=2, name="Orphan")
        state_manager.register_seam("s1", "A", "top", "B", "bottom")
        v = GarmentValidator(state_manager)
        result = v.validate()
        assert any("Orphan" in w for w in result.warnings)

    def test_no_orphans_when_no_seams(self, state_manager):
        """Without any seams, orphan check should pass (all are orphans)."""
        state_manager.register_pattern(index=0, name="A")
        v = GarmentValidator(state_manager)
        result = v.validate()
        assert "warn_orphan_pieces" in result.checks_passed

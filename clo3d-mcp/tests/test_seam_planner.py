"""
Tests for seam_planner.py — warn vs strict mode, length checking, plan execution.
"""

import os
import json
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from semantic.state_manager import StateManager
from semantic.seam_planner import SeamPlanner, SeamPlanResult, FullSeamPlanResult


@pytest.fixture(autouse=True)
def clean_env():
    """Clear seam-related env vars between tests."""
    for var in ("CLO_MCP_SEAM_TOLERANCE", "CLO_MCP_SEAM_MODE", "CLO_MCP_STATE_PATH"):
        os.environ.pop(var, None)
    yield
    for var in ("CLO_MCP_SEAM_TOLERANCE", "CLO_MCP_SEAM_MODE", "CLO_MCP_STATE_PATH"):
        os.environ.pop(var, None)


@pytest.fixture
def tmp_state_path(tmp_path):
    path = str(tmp_path / "test_state.json")
    os.environ["CLO_MCP_STATE_PATH"] = path
    return path


def _make_bridge_fn(responses=None):
    """Create a mock bridge function that returns predefined responses."""
    call_log = []
    if responses is None:
        responses = {}

    def bridge_fn(action, params=None):
        call_log.append({"action": action, "params": params})
        if action in responses:
            return responses[action]
        return {"success": True, "seam_name": "mock_seam"}

    bridge_fn.call_log = call_log
    return bridge_fn


def _register_test_patterns(state, with_geometry=True):
    """Register two rectangle test patterns in state."""
    edges_a = {"top": 1, "bottom": 3, "left": 0, "right": 2}
    edges_b = {"top": 1, "bottom": 3, "left": 0, "right": 2}

    geom_a = {
        "top": {"arc_length": 300.0, "line_index": 1},
        "bottom": {"arc_length": 300.0, "line_index": 3},
        "left": {"arc_length": 500.0, "line_index": 0},
        "right": {"arc_length": 500.0, "line_index": 2},
    } if with_geometry else {}

    geom_b = {
        "top": {"arc_length": 300.0, "line_index": 1},
        "bottom": {"arc_length": 300.0, "line_index": 3},
        "left": {"arc_length": 500.0, "line_index": 0},
        "right": {"arc_length": 500.0, "line_index": 2},
    } if with_geometry else {}

    state.register_pattern(
        index=0, name="Front", role="front",
        edges=edges_a, edge_geometry=geom_a,
        pattern_json_snapshot={"creation_points": [[0,0,0],[0,500,0],[300,500,0],[300,0,0]]},
    )
    state.register_pattern(
        index=1, name="Back", role="back",
        edges=edges_b, edge_geometry=geom_b,
        pattern_json_snapshot={"creation_points": [[400,0,0],[400,500,0],[700,500,0],[700,0,0]]},
    )


class TestSeamPlannerWarnMode:
    """Test seam planner in default warn mode."""

    def test_valid_seam(self, tmp_state_path):
        bridge = _make_bridge_fn()
        state = StateManager(bridge_fn=bridge)
        _register_test_patterns(state)
        planner = SeamPlanner(state=state, bridge_fn=bridge)

        result = planner.plan_seam("Front", "left", "Back", "right")
        assert result.success
        assert result.seam_name is not None

    def test_seam_recorded_in_state(self, tmp_state_path):
        bridge = _make_bridge_fn()
        state = StateManager(bridge_fn=bridge)
        _register_test_patterns(state)
        planner = SeamPlanner(state=state, bridge_fn=bridge)

        planner.plan_seam("Front", "left", "Back", "right", label="side_seam")
        seams = state.get_state()["seams"]
        assert len(seams) == 1
        assert seams[0]["group_name"] == "side_seam"

    def test_missing_pattern_fails(self, tmp_state_path):
        bridge = _make_bridge_fn()
        state = StateManager(bridge_fn=bridge)
        planner = SeamPlanner(state=state, bridge_fn=bridge)

        result = planner.plan_seam("Nonexistent", "left", "Back", "right")
        assert not result.success
        assert "not found" in result.error

    def test_missing_edge_fails(self, tmp_state_path):
        bridge = _make_bridge_fn()
        state = StateManager(bridge_fn=bridge)
        _register_test_patterns(state)
        planner = SeamPlanner(state=state, bridge_fn=bridge)

        result = planner.plan_seam("Front", "nonexistent_edge", "Back", "right")
        assert not result.success
        assert "not found" in result.error

    def test_bridge_error_fails(self, tmp_state_path):
        bridge = _make_bridge_fn({"add_seam": {"error": "CLO crashed"}})
        state = StateManager(bridge_fn=bridge)
        _register_test_patterns(state)
        planner = SeamPlanner(state=state, bridge_fn=bridge)

        result = planner.plan_seam("Front", "left", "Back", "right")
        assert not result.success
        assert "Bridge error" in result.error

    def test_length_mismatch_warns(self, tmp_state_path):
        """In warn mode, length mismatch produces a warning but still succeeds."""
        bridge = _make_bridge_fn()
        state = StateManager(bridge_fn=bridge)

        # Register patterns with different edge lengths
        state.register_pattern(
            index=0, name="Front", edges={"left": 0},
            edge_geometry={"left": {"arc_length": 500.0}},
        )
        state.register_pattern(
            index=1, name="Back", edges={"right": 2},
            edge_geometry={"right": {"arc_length": 300.0}},
        )

        planner = SeamPlanner(state=state, bridge_fn=bridge)
        result = planner.plan_seam("Front", "left", "Back", "right")

        assert result.success
        assert any("mismatch" in w.lower() for w in result.warnings)

    def test_matching_lengths_no_warning(self, tmp_state_path):
        """Matching edge lengths produce no warning."""
        bridge = _make_bridge_fn()
        state = StateManager(bridge_fn=bridge)
        _register_test_patterns(state)
        planner = SeamPlanner(state=state, bridge_fn=bridge)

        result = planner.plan_seam("Front", "left", "Back", "right")
        assert result.success
        mismatch_warnings = [w for w in result.warnings if "mismatch" in w.lower()]
        assert len(mismatch_warnings) == 0


class TestSeamPlannerStrictMode:
    """Test seam planner in strict mode."""

    def test_strict_blocks_mismatch(self, tmp_state_path):
        os.environ["CLO_MCP_SEAM_MODE"] = "strict"
        bridge = _make_bridge_fn()
        state = StateManager(bridge_fn=bridge)

        state.register_pattern(
            index=0, name="Front", edges={"left": 0},
            edge_geometry={"left": {"arc_length": 500.0}},
        )
        state.register_pattern(
            index=1, name="Back", edges={"right": 2},
            edge_geometry={"right": {"arc_length": 300.0}},
        )

        planner = SeamPlanner(state=state, bridge_fn=bridge)
        result = planner.plan_seam("Front", "left", "Back", "right")

        assert not result.success
        assert "mismatch" in result.error.lower()
        assert "strict" in result.hint.lower()

    def test_strict_allows_matching(self, tmp_state_path):
        os.environ["CLO_MCP_SEAM_MODE"] = "strict"
        bridge = _make_bridge_fn()
        state = StateManager(bridge_fn=bridge)
        _register_test_patterns(state)
        planner = SeamPlanner(state=state, bridge_fn=bridge)

        result = planner.plan_seam("Front", "left", "Back", "right")
        assert result.success

    def test_strict_blocks_zero_length(self, tmp_state_path):
        os.environ["CLO_MCP_SEAM_MODE"] = "strict"
        bridge = _make_bridge_fn()
        state = StateManager(bridge_fn=bridge)

        state.register_pattern(
            index=0, name="Front", edges={"left": 0},
            edge_geometry={"left": {"arc_length": 0.0}},
        )
        state.register_pattern(
            index=1, name="Back", edges={"right": 2},
            edge_geometry={"right": {"arc_length": 500.0}},
        )

        planner = SeamPlanner(state=state, bridge_fn=bridge)
        result = planner.plan_seam("Front", "left", "Back", "right")
        assert not result.success
        assert "zero-length" in result.error.lower()


class TestSeamPlannerTolerance:
    def test_custom_tolerance(self, tmp_state_path):
        """Custom tolerance from env var is respected."""
        os.environ["CLO_MCP_SEAM_TOLERANCE"] = "0.50"  # 50% tolerance
        bridge = _make_bridge_fn()
        state = StateManager(bridge_fn=bridge)

        state.register_pattern(
            index=0, name="Front", edges={"left": 0},
            edge_geometry={"left": {"arc_length": 500.0}},
        )
        state.register_pattern(
            index=1, name="Back", edges={"right": 2},
            edge_geometry={"right": {"arc_length": 300.0}},
        )

        planner = SeamPlanner(state=state, bridge_fn=bridge)
        # 40% mismatch, within 50% tolerance
        result = planner.plan_seam("Front", "left", "Back", "right")
        assert result.success
        mismatch_warnings = [w for w in result.warnings if "mismatch" in w.lower()]
        assert len(mismatch_warnings) == 0


class TestSeamPlannerFallback:
    def test_fallback_to_creation_points(self, tmp_state_path):
        """Length check falls back to creation points when edge_geometry is empty."""
        os.environ["CLO_MCP_SEAM_MODE"] = "strict"
        bridge = _make_bridge_fn()
        state = StateManager(bridge_fn=bridge)

        # Register without edge_geometry but with creation_points
        state.register_pattern(
            index=0, name="Front", edges={"left": 0, "top": 1, "right": 2, "bottom": 3},
            edge_geometry={},
            pattern_json_snapshot={"creation_points": [[0,0,0],[0,500,0],[300,500,0],[300,0,0]]},
        )
        state.register_pattern(
            index=1, name="Back", edges={"left": 0, "top": 1, "right": 2, "bottom": 3},
            edge_geometry={},
            pattern_json_snapshot={"creation_points": [[400,0,0],[400,500,0],[700,500,0],[700,0,0]]},
        )

        planner = SeamPlanner(state=state, bridge_fn=bridge)
        result = planner.plan_seam("Front", "left", "Back", "right")
        # Both sides are 500mm, should succeed
        assert result.success


class TestExecuteSeamPlan:
    def test_full_plan_success(self, tmp_state_path):
        bridge = _make_bridge_fn()
        state = StateManager(bridge_fn=bridge)
        _register_test_patterns(state)
        planner = SeamPlanner(state=state, bridge_fn=bridge)

        plan = [
            {"pattern_a": "Front", "edge_a": "left", "pattern_b": "Back",
             "edge_b": "right", "label": "side_seam"},
        ]
        result = planner.execute_seam_plan(plan)
        assert result.success
        assert len(result.seams_created) == 1

    def test_missing_pattern_pre_check(self, tmp_state_path):
        bridge = _make_bridge_fn()
        state = StateManager(bridge_fn=bridge)
        planner = SeamPlanner(state=state, bridge_fn=bridge)

        plan = [
            {"pattern_a": "Missing_A", "edge_a": "left", "pattern_b": "Missing_B",
             "edge_b": "right", "label": "test"},
        ]
        result = planner.execute_seam_plan(plan)
        assert not result.success
        assert "Missing patterns" in result.error

    def test_partial_failure(self, tmp_state_path):
        bridge = _make_bridge_fn()
        state = StateManager(bridge_fn=bridge)
        _register_test_patterns(state)
        planner = SeamPlanner(state=state, bridge_fn=bridge)

        plan = [
            {"pattern_a": "Front", "edge_a": "left", "pattern_b": "Back",
             "edge_b": "right", "label": "good_seam"},
            {"pattern_a": "Front", "edge_a": "nonexistent", "pattern_b": "Back",
             "edge_b": "right", "label": "bad_seam"},
        ]
        result = planner.execute_seam_plan(plan)
        assert not result.success
        assert len(result.seams_created) == 1
        assert len(result.seams_failed) == 1

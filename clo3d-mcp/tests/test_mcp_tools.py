"""
Tests for MCP tool-level behaviors with mocked bridge.

Tests the tools defined in mcp_server.py by mocking _send_to_bridge
and verifying correct behavior of create_piece, reclassify_piece,
reclassify_all, build_tshirt (staged), and health.
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def clean_env(tmp_path):
    """Reset state singletons and env vars between tests."""
    path = str(tmp_path / "test_state.json")
    os.environ["CLO_MCP_STATE_PATH"] = path
    os.environ.pop("CLO_MCP_SEAM_MODE", None)
    os.environ.pop("CLO_MCP_SEAM_TOLERANCE", None)

    import mcp_server
    mcp_server._state_manager = None
    mcp_server._seam_planner = None

    yield

    mcp_server._state_manager = None
    mcp_server._seam_planner = None
    os.environ.pop("CLO_MCP_STATE_PATH", None)


def _mock_bridge(action, params=None):
    """Mock bridge that simulates CLO responses."""
    pattern_counter = getattr(_mock_bridge, "_counter", 0)

    if action == "ping":
        return {"success": True, "message": "pong"}
    elif action == "create_pattern":
        _mock_bridge._counter = pattern_counter + 1
        return {"success": True, "pattern_index": pattern_counter}
    elif action == "set_pattern_name":
        return {"success": True}
    elif action == "add_seam":
        return {"success": True, "seam_name": "mock_seam"}
    elif action == "add_fabric":
        return {"success": True, "fabric_index": 0}
    elif action == "assign_fabric":
        return {"success": True}
    elif action == "simulate":
        return {"success": True, "frames": params.get("frames", 100) if params else 100}
    elif action == "get_pattern_count":
        return {"success": True, "pattern_count": pattern_counter}
    elif action == "get_pattern_name":
        return {"success": True, "name": f"pattern_{params['pattern_index']}"}
    elif action == "export_pattern_json":
        return {"success": False, "error": "Not available in mock"}
    else:
        return {"success": True}


class TestCreatePiece:
    def test_creates_and_classifies(self):
        import mcp_server
        _mock_bridge._counter = 0

        with patch.object(mcp_server, "_send_to_bridge", side_effect=_mock_bridge):
            result_str = mcp_server.create_piece(
                name="TestPiece",
                points=[[0,0,0], [0,500,0], [300,500,0], [300,0,0]],
                role="test_role",
            )
        result = json.loads(result_str)
        assert result["success"]
        assert result["name"] == "TestPiece"
        assert "top" in result["edges"]
        assert "bottom" in result["edges"]
        assert "left" in result["edges"]
        assert "right" in result["edges"]

    def test_edge_geometry_stored(self):
        import mcp_server
        _mock_bridge._counter = 0

        with patch.object(mcp_server, "_send_to_bridge", side_effect=_mock_bridge):
            mcp_server.create_piece(
                name="TestPiece",
                points=[[0,0,0], [0,500,0], [300,500,0], [300,0,0]],
                role="test_role",
            )
            state = mcp_server._get_state()
            entry = state.get_pattern_by_name("TestPiece")

        assert entry is not None
        geom = entry.get("edge_geometry", {})
        assert "top" in geom
        assert geom["top"]["arc_length"] > 0

    def test_bridge_error(self):
        import mcp_server

        def failing_bridge(action, params=None):
            if action == "create_pattern":
                return {"error": "CLO not running"}
            return {"success": True}

        with patch.object(mcp_server, "_send_to_bridge", side_effect=failing_bridge):
            result_str = mcp_server.create_piece(
                name="Fail", points=[[0,0,0],[0,100,0],[100,100,0],[100,0,0]],
            )
        result = json.loads(result_str)
        assert not result["success"]


class TestReclassifyPiece:
    def test_reclassify_from_snapshot(self):
        import mcp_server
        _mock_bridge._counter = 0

        with patch.object(mcp_server, "_send_to_bridge", side_effect=_mock_bridge):
            mcp_server.create_piece(
                name="Front",
                points=[[0,0,0], [0,500,0], [300,500,0], [300,0,0]],
                role="front",
            )
            result_str = mcp_server.reclassify_piece(pattern_name="Front")

        result = json.loads(result_str)
        assert result["success"]
        assert "edges" in result
        assert result["edges"]["top"] == 1

    def test_reclassify_missing_pattern(self):
        import mcp_server

        with patch.object(mcp_server, "_send_to_bridge", side_effect=_mock_bridge):
            result_str = mcp_server.reclassify_piece(pattern_name="Nonexistent")

        result = json.loads(result_str)
        assert not result["success"]
        assert "not found" in result["error"]


class TestReclassifyAll:
    def test_reclassify_all_patterns(self):
        import mcp_server
        _mock_bridge._counter = 0

        with patch.object(mcp_server, "_send_to_bridge", side_effect=_mock_bridge):
            mcp_server.create_piece(
                name="Front", points=[[0,0,0],[0,500,0],[300,500,0],[300,0,0]],
            )
            mcp_server.create_piece(
                name="Back", points=[[400,0,0],[400,500,0],[700,500,0],[700,0,0]],
            )
            result_str = mcp_server.reclassify_all()

        result = json.loads(result_str)
        assert result["success"]
        assert len(result["reclassified"]) == 2


class TestBuildTshirtStaged:
    def test_build_returns_stages(self):
        import mcp_server
        _mock_bridge._counter = 0

        with patch.object(mcp_server, "_send_to_bridge", side_effect=_mock_bridge):
            result_str = mcp_server.build_tshirt()

        result = json.loads(result_str)
        assert result["success"]
        assert "correlation_id" in result
        assert "server_version" in result
        assert "data" in result

        data = result["data"]
        assert "stages" in data
        stage_names = [s["stage"] for s in data["stages"]]
        assert "plan" in stage_names
        assert "create_pieces" in stage_names
        assert "fabric" in stage_names
        assert "sew_seams" in stage_names
        assert "simulate" in stage_names

    def test_build_pieces_stage_success(self):
        import mcp_server
        _mock_bridge._counter = 0

        with patch.object(mcp_server, "_send_to_bridge", side_effect=_mock_bridge):
            result_str = mcp_server.build_tshirt()

        result = json.loads(result_str)
        data = result["data"]
        pieces_stage = next(s for s in data["stages"] if s["stage"] == "create_pieces")
        assert pieces_stage["success"]
        assert len(pieces_stage["pieces_created"]) == 4

    def test_build_piece_failure_halts(self):
        import mcp_server

        call_count = [0]

        def bridge_fail_create(action, params=None):
            if action == "create_pattern":
                return {"error": "CLO crashed"}
            return _mock_bridge(action, params)

        with patch.object(mcp_server, "_send_to_bridge", side_effect=bridge_fail_create):
            result_str = mcp_server.build_tshirt()

        result = json.loads(result_str)
        assert not result["success"]
        assert result["error_code"] == "STAGE_FAILED"

    def test_build_fabric_skipped(self):
        import mcp_server
        _mock_bridge._counter = 0

        with patch.object(mcp_server, "_send_to_bridge", side_effect=_mock_bridge):
            result_str = mcp_server.build_tshirt(fabric_path="")

        result = json.loads(result_str)
        data = result["data"]
        fabric_stage = next(s for s in data["stages"] if s["stage"] == "fabric")
        assert fabric_stage["skipped"]


class TestHealthEndpoint:
    def test_health_response_format(self):
        import mcp_server
        _mock_bridge._counter = 0

        with patch.object(mcp_server, "_send_to_bridge", side_effect=_mock_bridge):
            result_str = mcp_server.health()

        result = json.loads(result_str)
        assert result["success"]
        assert "correlation_id" in result
        assert "server_version" in result
        data = result["data"]
        assert "bridge_connected" in data
        assert "garment_types" in data
        assert "seam_mode" in data
        assert "seam_tolerance" in data
        assert "state_version" in data
        assert "pattern_count" in data

    def test_health_bridge_down(self):
        import mcp_server

        def bridge_down(action, params=None):
            return {"error": "Connection refused", "code": "BRIDGE_UNAVAILABLE"}

        with patch.object(mcp_server, "_send_to_bridge", side_effect=bridge_down):
            result_str = mcp_server.health()

        result = json.loads(result_str)
        assert result["success"]  # Health endpoint itself succeeds
        data = result["data"]
        assert not data["bridge_connected"]

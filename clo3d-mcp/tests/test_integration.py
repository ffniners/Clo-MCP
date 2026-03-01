"""
Integration-style tests using a fake bridge socket.

Starts a local TCP server that mimics the CLO bridge, then runs
end-to-end flows through the real MCP server code.
"""

import json
import os
import socket
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class FakeBridge:
    """A fake TCP bridge server for integration testing."""

    def __init__(self, host="127.0.0.1", port=0):
        self.host = host
        self.port = port
        self.server = None
        self._thread = None
        self._running = False
        self._pattern_counter = 0
        self._patterns = {}

    def start(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.port = self.server.getsockname()[1]  # Get assigned port
        self.server.listen(5)
        self.server.settimeout(1.0)
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self.server:
            self.server.close()

    def _accept_loop(self):
        while self._running:
            try:
                conn, addr = self.server.accept()
                self._handle_client(conn)
            except socket.timeout:
                continue
            except OSError:
                break

    def _handle_client(self, conn):
        try:
            buf = b""
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                buf += data
                if b"\n" in buf:
                    break
            line = buf.split(b"\n", 1)[0].decode("utf-8").strip()
            if line:
                response = self._dispatch(json.loads(line))
                conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
        except Exception as e:
            try:
                conn.sendall((json.dumps({"error": str(e)}) + "\n").encode("utf-8"))
            except Exception:
                pass
        finally:
            conn.close()

    def _dispatch(self, cmd):
        action = cmd.get("action", "")
        params = cmd.get("params", {})

        if action == "ping":
            return {"success": True, "message": "pong"}
        elif action == "create_pattern":
            idx = self._pattern_counter
            self._pattern_counter += 1
            return {"success": True, "pattern_index": idx}
        elif action == "set_pattern_name":
            idx = params.get("pattern_index", 0)
            self._patterns[idx] = params.get("name", "")
            return {"success": True}
        elif action == "get_pattern_count":
            return {"success": True, "pattern_count": self._pattern_counter}
        elif action == "get_pattern_name":
            idx = params.get("pattern_index", 0)
            return {"success": True, "name": self._patterns.get(idx, ""),
                    "pattern_index": idx}
        elif action == "get_line_count":
            return {"success": True, "line_count": 4}
        elif action == "add_seam":
            return {"success": True, "seam_name": "test_seam"}
        elif action == "add_fabric":
            return {"success": True, "fabric_index": 0}
        elif action == "assign_fabric":
            return {"success": True}
        elif action == "simulate":
            return {"success": True, "frames": params.get("frames", 100)}
        elif action == "export_pattern_json":
            return {"success": False, "error": "Not implemented in fake bridge"}
        elif action == "get_scene_state":
            return {
                "success": True,
                "patterns": [{"index": i, "name": n} for i, n in self._patterns.items()],
                "fabrics": [],
                "seams": [],
            }
        else:
            return {"error": f"Unknown action: {action}"}


@pytest.fixture
def fake_bridge():
    """Start a fake bridge server on a random port."""
    bridge = FakeBridge()
    bridge.start()
    yield bridge
    bridge.stop()


@pytest.fixture(autouse=True)
def clean_state(tmp_path):
    """Reset state and env between tests."""
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


class TestFakeBridgeIntegration:
    """End-to-end tests through the real MCP server code using a fake bridge."""

    def test_ping_via_real_socket(self, fake_bridge):
        import mcp_server
        # Point MCP server at the fake bridge port
        original_port = mcp_server.BRIDGE_PORT
        mcp_server.BRIDGE_PORT = fake_bridge.port
        try:
            result_str = mcp_server.ping()
            result = json.loads(result_str)
            assert result["success"]
            assert result["message"] == "pong"
        finally:
            mcp_server.BRIDGE_PORT = original_port

    def test_create_piece_integration(self, fake_bridge):
        import mcp_server
        original_port = mcp_server.BRIDGE_PORT
        mcp_server.BRIDGE_PORT = fake_bridge.port
        try:
            result_str = mcp_server.create_piece(
                name="IntegrationTest",
                points=[[0,0,0], [0,500,0], [300,500,0], [300,0,0]],
                role="test_piece",
            )
            result = json.loads(result_str)
            assert result["success"]
            assert result["pattern_index"] == 0
            assert "top" in result["edges"]

            # Verify state was populated
            state = mcp_server._get_state()
            entry = state.get_pattern_by_name("IntegrationTest")
            assert entry is not None
            assert entry["role"] == "test_piece"
        finally:
            mcp_server.BRIDGE_PORT = original_port

    def test_create_and_sew_integration(self, fake_bridge):
        import mcp_server
        original_port = mcp_server.BRIDGE_PORT
        mcp_server.BRIDGE_PORT = fake_bridge.port
        try:
            # Create two pieces
            mcp_server.create_piece(
                name="Front",
                points=[[0,0,0], [0,500,0], [300,500,0], [300,0,0]],
                role="front",
            )
            mcp_server.create_piece(
                name="Back",
                points=[[400,0,0], [400,500,0], [700,500,0], [700,0,0]],
                role="back",
            )

            # Sew them
            result_str = mcp_server.sew_pieces(
                pattern_a_name="Front", edge_a="left",
                pattern_b_name="Back", edge_b="right",
            )
            result = json.loads(result_str)
            assert result["success"]

            # Verify seam in state
            state_data = mcp_server._get_state().get_state()
            assert len(state_data["seams"]) == 1
        finally:
            mcp_server.BRIDGE_PORT = original_port

    def test_build_tshirt_integration(self, fake_bridge):
        import mcp_server
        original_port = mcp_server.BRIDGE_PORT
        mcp_server.BRIDGE_PORT = fake_bridge.port
        try:
            result_str = mcp_server.build_tshirt(
                chest_width_mm=500,
                body_length_mm=700,
            )
            result = json.loads(result_str)
            assert result["success"]
            assert "correlation_id" in result
            assert len(result["data"]["pieces_created"]) == 4

            # Verify state
            state_data = mcp_server._get_state().get_state()
            assert len(state_data["patterns"]) == 4
            assert len(state_data["seams"]) == 6
        finally:
            mcp_server.BRIDGE_PORT = original_port

    def test_health_with_live_bridge(self, fake_bridge):
        import mcp_server
        original_port = mcp_server.BRIDGE_PORT
        mcp_server.BRIDGE_PORT = fake_bridge.port
        try:
            result_str = mcp_server.health()
            result = json.loads(result_str)
            assert result["success"]
            assert result["data"]["bridge_connected"]
        finally:
            mcp_server.BRIDGE_PORT = original_port

    def test_load_state_resyncs(self, fake_bridge):
        import mcp_server
        original_port = mcp_server.BRIDGE_PORT
        mcp_server.BRIDGE_PORT = fake_bridge.port
        try:
            # Create a piece
            mcp_server.create_piece(
                name="SyncTest",
                points=[[0,0,0], [0,100,0], [100,100,0], [100,0,0]],
            )

            # Reload state (simulates restart)
            result_str = mcp_server.load_state()
            result = json.loads(result_str)
            assert result["success"]
        finally:
            mcp_server.BRIDGE_PORT = original_port

"""
CLO3D MCP Server — external process that exposes CLO3D tools to Claude.
Communicates with the CLO bridge plugin over TCP (127.0.0.1:9876).
"""

import json
import socket
from typing import Any

from mcp.server.fastmcp import FastMCP

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 9876
SOCKET_TIMEOUT = 30  # seconds

mcp = FastMCP("clo3d")

# ---------------------------------------------------------------------------
# Bridge communication
# ---------------------------------------------------------------------------


def _send_to_bridge(action: str, params: dict | None = None) -> dict:
    """Send a command to the CLO bridge and return the parsed JSON response."""
    payload = {"action": action}
    if params:
        payload["params"] = params

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(SOCKET_TIMEOUT)
        sock.connect((BRIDGE_HOST, BRIDGE_PORT))
        sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))

        # Read until newline
        buf = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
            if b"\n" in buf:
                break
        sock.close()

        line = buf.split(b"\n", 1)[0].decode("utf-8").strip()
        if not line:
            return {"error": "Empty response from bridge"}
        return json.loads(line)
    except ConnectionRefusedError:
        return {"error": "Cannot connect to CLO bridge. Is CLO running with the bridge plugin loaded?"}
    except socket.timeout:
        return {"error": "Bridge response timed out"}
    except Exception as e:
        return {"error": f"Bridge communication error: {e}"}


def _format_result(result: dict) -> str:
    """Format a bridge response as a human-readable JSON string."""
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def ping() -> str:
    """Verify the CLO3D bridge plugin is running and responsive."""
    return _format_result(_send_to_bridge("ping"))


@mcp.tool()
def get_pattern_count() -> str:
    """Return the number of pattern pieces in the current CLO3D scene."""
    return _format_result(_send_to_bridge("get_pattern_count"))


@mcp.tool()
def create_pattern(points: list[list[float]]) -> str:
    """Create a pattern piece from a list of [x, y, curvature] points.

    Each point is [x, y, curvature] where curvature is:
      0 = straight line
      2 = curve
      3 = bezier

    Coordinates are in mm. Returns the new pattern index.

    Example — 300x500mm rectangle:
      points = [[0,0,0], [0,500,0], [300,500,0], [300,0,0]]
    """
    return _format_result(_send_to_bridge("create_pattern", {"points": points}))


@mcp.tool()
def set_pattern_name(pattern_index: int, name: str) -> str:
    """Set the name of a pattern piece by its index."""
    return _format_result(_send_to_bridge("set_pattern_name", {
        "pattern_index": pattern_index,
        "name": name,
    }))


@mcp.tool()
def get_line_count(pattern_index: int) -> str:
    """Get the number of outline lines (edges) on a pattern piece."""
    return _format_result(_send_to_bridge("get_line_count", {
        "pattern_index": pattern_index,
    }))


@mcp.tool()
def add_seam(
    pattern_a: int,
    line_a: int,
    pattern_b: int,
    line_b: int,
    direction_a: bool = True,
    direction_b: bool = True,
) -> str:
    """Sew two pattern edges together.

    Args:
        pattern_a: Index of the first pattern piece.
        line_a: Line index on pattern A to sew.
        pattern_b: Index of the second pattern piece.
        line_b: Line index on pattern B to sew.
        direction_a: Stitch direction for A (True=forward, False=backward).
        direction_b: Stitch direction for B (True=forward, False=backward).
    """
    return _format_result(_send_to_bridge("add_seam", {
        "pattern_a": pattern_a,
        "line_a": line_a,
        "pattern_b": pattern_b,
        "line_b": line_b,
        "direction_a": direction_a,
        "direction_b": direction_b,
    }))


@mcp.tool()
def add_fabric(file_path: str) -> str:
    """Load a .zfab fabric file into the CLO3D scene. Returns the fabric index."""
    return _format_result(_send_to_bridge("add_fabric", {"file_path": file_path}))


@mcp.tool()
def assign_fabric(fabric_index: int, pattern_index: int, assign_option: int = 1) -> str:
    """Assign a fabric to a pattern piece.

    Args:
        fabric_index: Fabric index in the object browser.
        pattern_index: Pattern piece index.
        assign_option: 1=current colorway, 2=all colorways (unlinked), 3=all colorways (linked).
    """
    return _format_result(_send_to_bridge("assign_fabric", {
        "fabric_index": fabric_index,
        "pattern_index": pattern_index,
        "assign_option": assign_option,
    }))


@mcp.tool()
def simulate(frames: int = 100) -> str:
    """Run cloth simulation for the given number of frames (default 100)."""
    return _format_result(_send_to_bridge("simulate", {"frames": frames}))


@mcp.tool()
def export_obj(file_path: str) -> str:
    """Export the current scene as an OBJ file to the given path."""
    return _format_result(_send_to_bridge("export_obj", {"file_path": file_path}))


@mcp.tool()
def export_render(file_path: str, render_all_colorways: bool = False) -> str:
    """Export a rendered image of the scene to the given path."""
    return _format_result(_send_to_bridge("export_render", {
        "file_path": file_path,
        "render_all_colorways": render_all_colorways,
    }))


@mcp.tool()
def export_techpack(file_path: str) -> str:
    """Export a tech pack JSON file to the given path."""
    return _format_result(_send_to_bridge("export_techpack", {"file_path": file_path}))


@mcp.tool()
def export_dxf(file_path: str) -> str:
    """Export patterns as a DXF file (for CAD/cutting machines) to the given path."""
    return _format_result(_send_to_bridge("export_dxf", {"file_path": file_path}))


@mcp.tool()
def get_scene_state() -> str:
    """Return a JSON summary of the current scene: patterns, fabrics, and seams."""
    return _format_result(_send_to_bridge("get_scene_state"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()

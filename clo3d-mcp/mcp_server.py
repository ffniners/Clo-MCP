"""
CLO3D MCP Server — external process that exposes CLO3D tools to Claude.
Communicates with the CLO bridge plugin over TCP (127.0.0.1:9876).

V1 tools: raw API access with explicit indices.
V2 tools: semantic layer — named pieces, edge labels, garment types.
V3 tools: reclassification, health/capabilities, transactional builds,
          correlation IDs, structured error codes.
"""

import json
import os
import socket
import sys
import uuid
import time
from dataclasses import asdict
from typing import Any

from mcp.server.fastmcp import FastMCP

# Add project root to path for semantic imports
sys.path.insert(0, os.path.dirname(__file__))

from semantic.geometry import (
    parse_points,
    build_edges_from_creation_points,
    build_edges_from_pattern_json,
    classify_edges,
    classify_edges_extended,
    extract_edge_geometry,
)
from semantic.state_manager import StateManager
from semantic.seam_planner import SeamPlanner
from semantic.garment_types import (
    derive_tshirt_pieces,
    derive_aline_skirt_pieces,
    get_garment_type,
    get_derivation_function,
    list_garment_types,
    load_garment_specs_from_dir,
    register_garment_type,
    DEFAULT_TSHIRT_MEASUREMENTS,
)

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 9876
SOCKET_TIMEOUT = 30  # seconds
SERVER_VERSION = "3.0.0"

mcp = FastMCP("clo3d")

# ---------------------------------------------------------------------------
# Standardized error codes (V3)
# ---------------------------------------------------------------------------

ERR_BRIDGE_UNAVAILABLE = "BRIDGE_UNAVAILABLE"
ERR_BRIDGE_TIMEOUT = "BRIDGE_TIMEOUT"
ERR_BRIDGE_ERROR = "BRIDGE_ERROR"
ERR_PATTERN_NOT_FOUND = "PATTERN_NOT_FOUND"
ERR_EDGE_NOT_FOUND = "EDGE_NOT_FOUND"
ERR_GARMENT_UNKNOWN = "GARMENT_UNKNOWN"
ERR_VALIDATION_FAILED = "VALIDATION_FAILED"
ERR_STAGE_FAILED = "STAGE_FAILED"

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
            return {"error": "Empty response from bridge", "code": ERR_BRIDGE_ERROR}
        return json.loads(line)
    except ConnectionRefusedError:
        return {"error": "Cannot connect to CLO bridge. Is CLO running with the bridge plugin loaded?",
                "code": ERR_BRIDGE_UNAVAILABLE}
    except socket.timeout:
        return {"error": "Bridge response timed out", "code": ERR_BRIDGE_TIMEOUT}
    except Exception as e:
        return {"error": f"Bridge communication error: {e}", "code": ERR_BRIDGE_ERROR}


def _format_result(result: dict) -> str:
    """Format a bridge response as a human-readable JSON string."""
    return json.dumps(result, indent=2)


def _v2_error(error: str, hint: str) -> str:
    """Return a structured V2 error response."""
    return json.dumps({"success": False, "error": error, "hint": hint}, indent=2)


def _v3_response(
    success: bool,
    data: dict | None = None,
    error: str | None = None,
    error_code: str | None = None,
    hint: str | None = None,
    warnings: list[str] | None = None,
    correlation_id: str | None = None,
) -> str:
    """Return a normalized V3 response envelope with correlation ID."""
    envelope: dict[str, Any] = {
        "success": success,
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "server_version": SERVER_VERSION,
        "timestamp": time.time(),
    }
    if data is not None:
        envelope["data"] = data
    if error is not None:
        envelope["error"] = error
    if error_code is not None:
        envelope["error_code"] = error_code
    if hint is not None:
        envelope["hint"] = hint
    if warnings:
        envelope["warnings"] = warnings
    return json.dumps(envelope, indent=2)


# ---------------------------------------------------------------------------
# State & planner singletons (lazy-initialized)
# ---------------------------------------------------------------------------

_state_manager: StateManager | None = None
_seam_planner: SeamPlanner | None = None


def _get_state() -> StateManager:
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager(bridge_fn=_send_to_bridge)
    return _state_manager


def _get_planner() -> SeamPlanner:
    global _seam_planner
    if _seam_planner is None:
        _seam_planner = SeamPlanner(
            state=_get_state(),
            bridge_fn=_send_to_bridge,
        )
    return _seam_planner


# ---------------------------------------------------------------------------
# Helper: create pattern + classify edges + register in state
# ---------------------------------------------------------------------------


def _create_and_register_piece(
    points: list[list[float]],
    name: str,
    role: str = "",
) -> dict:
    """
    Create a pattern in CLO, classify its edges, register in state.
    Returns a result dict with pattern_index, edges, and any warnings.
    """
    # 1. Create pattern in CLO
    result = _send_to_bridge("create_pattern", {"points": points})
    if "error" in result:
        return {"success": False, "error": result["error"],
                "hint": "Check CLO is running and bridge is loaded."}

    pattern_index = result["pattern_index"]

    # 2. Set name
    _send_to_bridge("set_pattern_name", {
        "pattern_index": pattern_index, "name": name
    })

    # 3. Classify edges from creation points
    parsed = parse_points(points)
    edges = build_edges_from_creation_points(parsed)

    # Use extended classification for garment pieces (handles top_left, etc.)
    classification = classify_edges_extended(edges)

    # 4. Extract normalized edge geometry for storage (V3)
    edge_geometry = extract_edge_geometry(edges, classification.labels)

    # 5. Register in state
    state = _get_state()
    state.register_pattern(
        index=pattern_index,
        name=name,
        role=role,
        edges=classification.labels,
        pattern_json_snapshot={"creation_points": points},
        edge_geometry=edge_geometry,
    )

    return {
        "success": True,
        "pattern_index": pattern_index,
        "name": name,
        "role": role,
        "edges": classification.labels,
        "warnings": classification.warnings,
    }


def _reclassify_piece_internal(pattern_name: str) -> dict:
    """
    Re-derive edge labels for an existing piece from its stored snapshot.
    Uses PatternJSON from bridge if available, otherwise falls back to
    creation points in the snapshot.
    """
    state = _get_state()
    entry = state.get_pattern_by_name(pattern_name)
    if not entry:
        return {
            "success": False,
            "error": f"Pattern '{pattern_name}' not found in state.",
            "error_code": ERR_PATTERN_NOT_FOUND,
        }

    pattern_index = entry["index"]
    edges = None

    # Try PatternJSON from bridge first (authoritative after edits)
    bridge_result = _send_to_bridge("export_pattern_json", {})
    if bridge_result.get("success") and "pattern_json" in bridge_result:
        pj = bridge_result["pattern_json"]
        # Find matching pattern in the exported JSON
        patterns = pj.get("Patterns", pj.get("patterns", []))
        if isinstance(patterns, list) and pattern_index < len(patterns):
            pattern_data = patterns[pattern_index]
            edges = build_edges_from_pattern_json(pattern_data)
            state.update_pattern_json_snapshot(pattern_index, pattern_data)

    # Fallback: use stored creation points
    if not edges:
        snapshot = entry.get("pattern_json_snapshot", {})
        creation_pts = snapshot.get("creation_points")
        if creation_pts:
            parsed = parse_points(creation_pts)
            edges = build_edges_from_creation_points(parsed)

    if not edges:
        return {
            "success": False,
            "error": "No geometry data available for reclassification.",
            "hint": "Recreate the piece or ensure CLO bridge is connected.",
        }

    classification = classify_edges_extended(edges)
    edge_geometry = extract_edge_geometry(edges, classification.labels)

    state.update_edges(pattern_index, classification.labels, edge_geometry)

    return {
        "success": True,
        "pattern_name": pattern_name,
        "edges": classification.labels,
        "warnings": classification.warnings,
    }


# ===========================================================================
# V1 MCP Tools (unchanged)
# ===========================================================================


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
    pattern_a: int, line_a: int,
    pattern_b: int, line_b: int,
    direction_a: bool = True, direction_b: bool = True,
) -> str:
    """Sew two pattern edges together (V1 — uses raw indices).

    Args:
        pattern_a: Index of the first pattern piece.
        line_a: Line index on pattern A to sew.
        pattern_b: Index of the second pattern piece.
        line_b: Line index on pattern B to sew.
        direction_a: Stitch direction for A (True=forward, False=backward).
        direction_b: Stitch direction for B (True=forward, False=backward).
    """
    return _format_result(_send_to_bridge("add_seam", {
        "pattern_a": pattern_a, "line_a": line_a,
        "pattern_b": pattern_b, "line_b": line_b,
        "direction_a": direction_a, "direction_b": direction_b,
    }))


@mcp.tool()
def add_fabric(file_path: str) -> str:
    """Load a .zfab fabric file into the CLO3D scene. Returns the fabric index."""
    return _format_result(_send_to_bridge("add_fabric", {"file_path": file_path}))


@mcp.tool()
def assign_fabric(fabric_index: int, pattern_index: int, assign_option: int = 1) -> str:
    """Assign a fabric to a pattern piece (V1 — uses raw indices).

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
    """Return a JSON summary of the current CLO scene: patterns, fabrics, and seams."""
    return _format_result(_send_to_bridge("get_scene_state"))


# ===========================================================================
# V2 MCP Tools — Semantic Layer
# ===========================================================================


@mcp.tool()
def create_piece(
    name: str,
    points: list[list[float]],
    role: str = "",
) -> str:
    """Create a named pattern piece, classify its edges, and register in state.

    Creates the pattern in CLO, automatically classifies edges (top, bottom,
    left, right, curved, longest, shortest, etc.), and stores everything in
    the garment state file.

    Args:
        name: Human-readable name for the piece (e.g. "Front_Bodice").
        points: List of [x, y, curvature] points defining the shape (mm).
                Curvature: 0=straight, 2=curve, 3=bezier.
        role: Optional garment role (e.g. "front_bodice", "sleeve_left").

    Returns piece summary with resolved edge labels.
    """
    result = _create_and_register_piece(points, name, role)
    return json.dumps(result, indent=2)


@mcp.tool()
def sew_pieces(
    pattern_a_name: str,
    edge_a: str,
    pattern_b_name: str,
    edge_b: str,
    flip: bool = False,
) -> str:
    """Sew two named pieces together by semantic edge label.

    Uses the geometry resolver to find the correct line indices.
    Validates edge lengths match within tolerance before sewing.

    Args:
        pattern_a_name: Name of the first pattern piece.
        edge_a: Edge label on pattern A (e.g. "left", "top", "right").
        pattern_b_name: Name of the second pattern piece.
        edge_b: Edge label on pattern B.
        flip: If True, reverse stitch direction on B (for opposing seams).
    """
    planner = _get_planner()
    result = planner.plan_seam(
        pattern_a_name=pattern_a_name,
        edge_a=edge_a,
        pattern_b_name=pattern_b_name,
        edge_b=edge_b,
        flip=flip,
    )

    return json.dumps({
        "success": result.success,
        "seam_name": result.seam_name,
        "error": result.error,
        "hint": result.hint,
        "warnings": result.warnings,
    }, indent=2)


@mcp.tool()
def sew_garment(garment_type: str = "t_shirt") -> str:
    """Execute the full seam plan for a garment type in one call.

    Validates all pieces exist in state first. Reports missing pieces
    before attempting any seams.

    Args:
        garment_type: Name of the garment type (currently: "t_shirt").
    """
    gt = get_garment_type(garment_type)
    if not gt:
        return _v2_error(
            f"Unknown garment type: {garment_type}",
            f"Available types: {list_garment_types()}"
        )

    # Convert SeamDefinition objects to dicts for the planner.
    # Map role names to actual pattern names via state.
    state = _get_state()
    seam_dicts = []
    for sd in gt.seam_plan:
        # Resolve role → pattern name
        entry_a = state.get_pattern_by_role(sd.pattern_a)
        entry_b = state.get_pattern_by_role(sd.pattern_b)
        name_a = entry_a["name"] if entry_a else sd.pattern_a
        name_b = entry_b["name"] if entry_b else sd.pattern_b

        seam_dicts.append({
            "pattern_a": name_a,
            "edge_a": sd.edge_a,
            "pattern_b": name_b,
            "edge_b": sd.edge_b,
            "flip": sd.flip,
            "label": sd.label,
        })

    planner = _get_planner()
    result = planner.execute_seam_plan(seam_dicts)

    return json.dumps({
        "success": result.success,
        "seams_created": result.seams_created,
        "seams_failed": result.seams_failed,
        "warnings": result.warnings,
        "error": result.error,
        "hint": result.hint,
    }, indent=2)


@mcp.tool()
def get_garment_state() -> str:
    """Return full current garment state as JSON.

    Includes all registered patterns (with edge labels), fabrics,
    seams, and any resolver warnings.
    """
    state = _get_state()
    return json.dumps(state.get_state(), indent=2)


@mcp.tool()
def load_state() -> str:
    """Reload garment state from disk and re-sync with CLO.

    Useful after CLO restart — updates pattern indices to match
    current CLO scene.
    """
    global _state_manager, _seam_planner
    _state_manager = StateManager(bridge_fn=_send_to_bridge)
    _seam_planner = None  # Will be recreated on next use

    warnings = _state_manager.sync_with_clo()
    return json.dumps({
        "success": True,
        "warnings": warnings,
        "state": _state_manager.get_state(),
    }, indent=2)


@mcp.tool()
def clear_state() -> str:
    """Wipe garment state file and reset to empty.

    Does NOT modify the CLO scene — only clears the local state file.
    """
    state = _get_state()
    state.clear()
    return json.dumps({"success": True, "message": "State cleared."}, indent=2)


@mcp.tool()
def add_fabric_named(file_path: str, name: str) -> str:
    """Load a .zfab fabric file and register it in state with a friendly name.

    Args:
        file_path: Path to the .zfab file.
        name: Human-readable name (e.g. "Cotton_Oxford").
    """
    result = _send_to_bridge("add_fabric", {"file_path": file_path})
    if "error" in result:
        return _v2_error(result["error"], "Check the file path exists and is a valid .zfab file.")

    fabric_index = result["fabric_index"]
    state = _get_state()
    state.register_fabric(index=fabric_index, name=name, path=file_path)

    return json.dumps({
        "success": True,
        "fabric_index": fabric_index,
        "name": name,
    }, indent=2)


@mcp.tool()
def assign_fabric_to_piece(fabric_name: str, piece_name: str) -> str:
    """Assign a named fabric to a named pattern piece.

    Args:
        fabric_name: Friendly name of the fabric (as registered with add_fabric_named).
        piece_name: Name of the pattern piece.
    """
    state = _get_state()
    fabric = state.get_fabric_by_name(fabric_name)
    if not fabric:
        return _v2_error(
            f"Fabric '{fabric_name}' not found in state.",
            "Use add_fabric_named to load a fabric first."
        )

    pattern = state.get_pattern_by_name(piece_name)
    if not pattern:
        return _v2_error(
            f"Pattern '{piece_name}' not found in state.",
            "Use create_piece to create the pattern first."
        )

    result = _send_to_bridge("assign_fabric", {
        "fabric_index": fabric["index"],
        "pattern_index": pattern["index"],
        "assign_option": 1,
    })
    if "error" in result:
        return _v2_error(result["error"], "Check CLO is running.")

    state.assign_fabric_to_pattern(fabric["index"], pattern["index"])

    return json.dumps({
        "success": True,
        "fabric": fabric_name,
        "piece": piece_name,
    }, indent=2)


@mcp.tool()
def build_tshirt(
    chest_width_mm: float = 500,
    body_length_mm: float = 700,
    shoulder_width_mm: float = 420,
    sleeve_length_mm: float = 220,
    sleeve_width_mm: float = 180,
    neck_drop_mm: float = 80,
    fabric_path: str = "",
    simulate_frames: int = 100,
) -> str:
    """Build a complete T-shirt: create pieces, sew seams, assign fabric, simulate.

    V3: Returns structured per-stage results with correct final success semantics.
    Each stage (pieces, fabric, seams, simulation) reports independently.

    Measurement parameters (all in mm):
        chest_width_mm: Full front panel width (default 500).
        body_length_mm: Shoulder to hem length (default 700).
        shoulder_width_mm: Shoulder point to shoulder point (default 420).
        sleeve_length_mm: Shoulder point to sleeve hem (default 220).
        sleeve_width_mm: Sleeve opening width at shoulder (default 180).
        neck_drop_mm: How far below shoulder the front neckline drops (default 80).
        fabric_path: Optional path to a .zfab file.
        simulate_frames: Frames to simulate (default 100).
    """
    correlation_id = str(uuid.uuid4())
    measurements = {
        "chest_width_mm": chest_width_mm,
        "body_length_mm": body_length_mm,
        "shoulder_width_mm": shoulder_width_mm,
        "sleeve_length_mm": sleeve_length_mm,
        "sleeve_width_mm": sleeve_width_mm,
        "neck_drop_mm": neck_drop_mm,
    }

    all_warnings: list[str] = []
    stages: list[dict] = []

    # === Stage 1: Plan — derive pattern coordinates ===
    pieces = derive_tshirt_pieces(measurements)
    stages.append({"stage": "plan", "success": True})

    # === Stage 2: Create pieces ===
    gt = get_garment_type("t_shirt")
    assert gt is not None

    piece_names: dict[str, str] = {}
    piece_errors: list[str] = []

    for piece_def in gt.pieces:
        role = piece_def.role
        name = role.replace("_", " ").title().replace(" ", "_")
        points = pieces[role]

        result = _create_and_register_piece(points, name, role)
        if not result.get("success"):
            piece_errors.append(f"Failed to create {name}: {result.get('error', 'unknown')}")
            continue
        piece_names[role] = name
        all_warnings.extend(result.get("warnings", []))

    pieces_success = len(piece_errors) == 0
    stages.append({
        "stage": "create_pieces",
        "success": pieces_success,
        "pieces_created": list(piece_names.values()),
        "errors": piece_errors if piece_errors else None,
    })

    if not pieces_success:
        return _v3_response(
            success=False,
            data={"stages": stages, "measurements": measurements},
            error=f"Piece creation failed: {piece_errors}",
            error_code=ERR_STAGE_FAILED,
            hint="Check CLO is running and bridge is loaded.",
            warnings=all_warnings,
            correlation_id=correlation_id,
        )

    # === Stage 3: Fabric (optional) ===
    fabric_stage: dict[str, Any] = {"stage": "fabric", "success": True, "skipped": True}
    if fabric_path:
        fabric_stage["skipped"] = False
        fab_result = _send_to_bridge("add_fabric", {"file_path": fabric_path})
        if "error" in fab_result:
            fabric_stage["success"] = False
            fabric_stage["error"] = fab_result["error"]
            all_warnings.append(f"Fabric load failed: {fab_result['error']}")
        else:
            fab_idx = fab_result["fabric_index"]
            state = _get_state()
            state.register_fabric(index=fab_idx, name="tshirt_fabric", path=fabric_path)
            for role, name in piece_names.items():
                pattern = state.get_pattern_by_name(name)
                if pattern:
                    _send_to_bridge("assign_fabric", {
                        "fabric_index": fab_idx,
                        "pattern_index": pattern["index"],
                        "assign_option": 1,
                    })
                    state.assign_fabric_to_pattern(fab_idx, pattern["index"])
    stages.append(fabric_stage)

    # === Stage 4: Sew seams ===
    state = _get_state()
    seam_dicts = []
    for sd in gt.seam_plan:
        entry_a = state.get_pattern_by_role(sd.pattern_a)
        entry_b = state.get_pattern_by_role(sd.pattern_b)
        if not entry_a or not entry_b:
            all_warnings.append(
                f"Skipping seam {sd.label}: missing piece "
                f"({sd.pattern_a} or {sd.pattern_b})"
            )
            continue
        seam_dicts.append({
            "pattern_a": entry_a["name"],
            "edge_a": sd.edge_a,
            "pattern_b": entry_b["name"],
            "edge_b": sd.edge_b,
            "flip": sd.flip,
            "label": sd.label,
        })

    planner = _get_planner()
    seam_result = planner.execute_seam_plan(seam_dicts)
    all_warnings.extend(seam_result.warnings)

    stages.append({
        "stage": "sew_seams",
        "success": seam_result.success,
        "seams_created": seam_result.seams_created,
        "seams_failed": seam_result.seams_failed if seam_result.seams_failed else None,
    })

    # === Stage 5: Simulate ===
    sim_result = _send_to_bridge("simulate", {"frames": simulate_frames})
    sim_success = "error" not in sim_result
    if not sim_success:
        all_warnings.append(f"Simulation error: {sim_result.get('error')}")
    stages.append({
        "stage": "simulate",
        "success": sim_success,
        "frames": simulate_frames,
    })

    # === Final result ===
    overall_success = pieces_success and seam_result.success
    final_state = _get_state().get_state()

    return _v3_response(
        success=overall_success,
        data={
            "measurements": measurements,
            "stages": stages,
            "pieces_created": list(piece_names.values()),
            "seams_created": seam_result.seams_created,
            "seams_failed": seam_result.seams_failed,
            "simulated_frames": simulate_frames,
            "fabric_loaded": bool(fabric_path),
            "state": final_state,
        },
        warnings=all_warnings,
        correlation_id=correlation_id,
    )


# ===========================================================================
# V3 MCP Tools — Reclassification
# ===========================================================================


@mcp.tool()
def reclassify_piece(pattern_name: str) -> str:
    """Reclassify edge labels for a pattern piece after manual CLO edits.

    Re-derives edge labels using PatternJSON from CLO (if available) or
    the stored creation points snapshot. Updates state with new labels
    and edge geometry.

    Args:
        pattern_name: Name of the pattern piece to reclassify.
    """
    result = _reclassify_piece_internal(pattern_name)
    return json.dumps(result, indent=2)


@mcp.tool()
def reclassify_all() -> str:
    """Reclassify edge labels for all registered pattern pieces.

    Useful after bulk manual edits in CLO. Updates all edge labels
    and geometry in state.
    """
    state = _get_state()
    state_data = state.get_state()
    results = []
    all_warnings: list[str] = []

    for key, entry in state_data.get("patterns", {}).items():
        name = entry.get("name", "")
        if not name:
            continue
        r = _reclassify_piece_internal(name)
        results.append(r)
        all_warnings.extend(r.get("warnings", []))

    all_success = all(r.get("success", False) for r in results)
    return json.dumps({
        "success": all_success,
        "reclassified": [r.get("pattern_name") for r in results if r.get("success")],
        "failed": [r for r in results if not r.get("success")],
        "warnings": all_warnings,
    }, indent=2)


# ===========================================================================
# V3 MCP Tools — Health / Capabilities
# ===========================================================================


@mcp.tool()
def health() -> str:
    """Report server health, bridge connectivity, and capabilities.

    Returns server version, state revision, bridge availability,
    registered garment types, and seam validation mode.
    """
    correlation_id = str(uuid.uuid4())

    # Check bridge
    bridge_result = _send_to_bridge("ping")
    bridge_ok = bridge_result.get("success", False)

    # State info
    state = _get_state()
    state_data = state.get_state()

    from semantic.seam_planner import _get_seam_mode, _get_seam_tolerance

    return _v3_response(
        success=True,
        data={
            "server_version": SERVER_VERSION,
            "bridge_connected": bridge_ok,
            "bridge_message": bridge_result.get("message") if bridge_ok else bridge_result.get("error"),
            "state_version": state_data.get("version"),
            "state_revision": state_data.get("revision"),
            "state_path": os.environ.get("CLO_MCP_STATE_PATH", "(default)"),
            "garment_types": list_garment_types(),
            "seam_mode": _get_seam_mode(),
            "seam_tolerance": _get_seam_tolerance(),
            "pattern_count": len(state_data.get("patterns", {})),
            "seam_count": len(state_data.get("seams", [])),
            "fabric_count": len(state_data.get("fabrics", {})),
        },
        correlation_id=correlation_id,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()

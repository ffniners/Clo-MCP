"""
CLO3D Bridge Plugin — loaded inside CLO via Plugin Manager.
Listens on 127.0.0.1:9876 for newline-delimited JSON commands from the MCP server.
Executes CLO Python API calls and returns JSON results.
"""

import socket
import json
import threading
import traceback

import pattern_api
import fabric_api
import export_api
import import_api
import utility_api

HOST = "127.0.0.1"
PORT = 9876
RECV_BUF = 65536

# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _handle_ping(params):
    return {"success": True, "message": "pong"}


def _handle_get_pattern_count(params):
    count = pattern_api.GetPatternCount()
    return {"success": True, "pattern_count": count}


def _handle_create_pattern(params):
    raw_points = params["points"]
    points = tuple((float(p[0]), float(p[1]), int(p[2])) for p in raw_points)
    idx = pattern_api.CreatePatternWithPoints(points)
    return {"success": True, "pattern_index": idx}


def _handle_set_pattern_name(params):
    idx = int(params["pattern_index"])
    name = str(params["name"])
    result = pattern_api.SetPatternName(idx, name)
    return {"success": bool(result)}


def _handle_get_line_count(params):
    idx = int(params["pattern_index"])
    count = pattern_api.GetLineCount(idx)
    return {"success": True, "line_count": count}


def _handle_add_seam(params):
    result = pattern_api.AddSeamlinePairGroup(
        int(params["pattern_a"]),
        int(params["line_a"]),
        int(params["pattern_b"]),
        int(params["line_b"]),
        bool(params.get("direction_a", True)),
        bool(params.get("direction_b", True)),
    )
    return {"success": True, "seam_name": str(result) if result else None}


def _handle_add_fabric(params):
    path = str(params["file_path"])
    idx = fabric_api.AddFabric(path)
    return {"success": True, "fabric_index": idx}


def _handle_assign_fabric(params):
    fabric_idx = int(params["fabric_index"])
    pattern_idx = int(params["pattern_index"])
    option = int(params.get("assign_option", 1))
    result = fabric_api.AssignFabricToPattern(fabric_idx, pattern_idx, option)
    return {"success": bool(result)}


def _handle_simulate(params):
    frames = int(params.get("frames", 100))
    utility_api.Simulate(frames)
    return {"success": True, "frames": frames}


def _handle_export_obj(params):
    path = str(params["file_path"])
    paths = export_api.ExportOBJ(path, _default_export_option())
    return {"success": True, "paths": _flatten(paths)}


def _handle_export_render(params):
    path = str(params["file_path"])
    render_all = bool(params.get("render_all_colorways", False))
    paths = export_api.ExportRenderingImage(path, render_all, 0)
    return {"success": True, "paths": _flatten(paths)}


def _handle_export_techpack(params):
    path = str(params["file_path"])
    export_api.ExportTechPack(path, _default_techpack_option())
    return {"success": True, "path": path}


def _handle_export_dxf(params):
    path = str(params["file_path"])
    result = export_api.ExportDXF(path, _default_dxf_option())
    return {"success": True, "path": str(result) if result else path}


def _handle_get_scene_state(params):
    pattern_count = pattern_api.GetPatternCount()
    patterns = []
    for i in range(pattern_count):
        name = pattern_api.GetPatternName(i)
        line_count = pattern_api.GetLineCount(i)
        fabric_idx = fabric_api.GetFabricIndexForPattern(i)
        patterns.append({
            "index": i,
            "name": name,
            "line_count": line_count,
            "fabric_index": fabric_idx,
        })

    fabric_count = fabric_api.GetFabricCount(True)
    fabrics = []
    for i in range(fabric_count):
        fname = fabric_api.GetFabricName(i)
        fabrics.append({"index": i, "name": fname})

    seam_count = pattern_api.GetSeamlinePairGroupCount()
    seams = []
    for i in range(seam_count):
        sname = pattern_api.GetSeamlinePairGroupName(i)
        seams.append({"index": i, "name": sname})

    return {
        "success": True,
        "patterns": patterns,
        "fabrics": fabrics,
        "seams": seams,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_export_option():
    """Return a minimal ImportExportOption."""
    try:
        import ApiTypes
        opt = ApiTypes.ImportExportOption()
        opt.scale = 1
        opt.bSaveInZip = False
        return opt
    except Exception:
        return None


def _default_techpack_option():
    try:
        import ApiTypes
        return ApiTypes.ExportTechpackOption()
    except Exception:
        return None


def _default_dxf_option():
    try:
        import ApiTypes
        return ApiTypes.ExportDxfOption()
    except Exception:
        return None


def _flatten(obj):
    """Flatten nested lists of paths into a single list of strings."""
    if obj is None:
        return []
    if isinstance(obj, str):
        return [obj]
    result = []
    for item in obj:
        if isinstance(item, (list, tuple)):
            result.extend(_flatten(item))
        else:
            result.append(str(item))
    return result


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

HANDLERS = {
    "ping": _handle_ping,
    "get_pattern_count": _handle_get_pattern_count,
    "create_pattern": _handle_create_pattern,
    "set_pattern_name": _handle_set_pattern_name,
    "get_line_count": _handle_get_line_count,
    "add_seam": _handle_add_seam,
    "add_fabric": _handle_add_fabric,
    "assign_fabric": _handle_assign_fabric,
    "simulate": _handle_simulate,
    "export_obj": _handle_export_obj,
    "export_render": _handle_export_render,
    "export_techpack": _handle_export_techpack,
    "export_dxf": _handle_export_dxf,
    "get_scene_state": _handle_get_scene_state,
}


def handle_command(raw_json: str) -> str:
    """Parse a JSON command, dispatch it, and return a JSON response string."""
    try:
        cmd = json.loads(raw_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})

    action = cmd.get("action")
    if not action:
        return json.dumps({"error": "Missing 'action' field"})

    handler = HANDLERS.get(action)
    if not handler:
        return json.dumps({"error": f"Unknown action: {action}"})

    params = cmd.get("params", {})
    try:
        result = handler(params)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": f"{action} failed: {e}", "traceback": traceback.format_exc()})


# ---------------------------------------------------------------------------
# TCP server — one connection at a time, newline-delimited JSON
# ---------------------------------------------------------------------------

def _client_session(conn: socket.socket, addr):
    """Handle a single client connection. Reads newline-delimited JSON."""
    buf = ""
    try:
        while True:
            data = conn.recv(RECV_BUF)
            if not data:
                break
            buf += data.decode("utf-8")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                response = handle_command(line)
                conn.sendall((response + "\n").encode("utf-8"))
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _run_server():
    """Main server loop. Binds to HOST:PORT and accepts connections."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    print(f"[CLO Bridge] Listening on {HOST}:{PORT}")
    while True:
        try:
            conn, addr = server.accept()
            print(f"[CLO Bridge] Connection from {addr}")
            t = threading.Thread(target=_client_session, args=(conn, addr), daemon=True)
            t.start()
        except Exception as e:
            print(f"[CLO Bridge] Accept error: {e}")


# ---------------------------------------------------------------------------
# Entry point — called when CLO loads this plugin
# ---------------------------------------------------------------------------

_server_thread = threading.Thread(target=_run_server, daemon=True)
_server_thread.start()
print("[CLO Bridge] Plugin loaded — server thread started")

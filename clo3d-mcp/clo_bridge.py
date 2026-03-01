"""
CLO3D Bridge Plugin — loaded inside CLO via Plugin Manager.
Listens on 127.0.0.1:9876 for newline-delimited JSON commands.
"""
import socket, json, os, tempfile, threading, traceback
import pattern_api, fabric_api, export_api, import_api, utility_api

HOST, PORT, RECV_BUF = "127.0.0.1", 9876, 65536

# -- V1 Handlers ----------------------------------------------------------

def _handle_ping(p):
    return {"success": True, "message": "pong"}

def _handle_get_pattern_count(p):
    return {"success": True, "pattern_count": pattern_api.GetPatternCount()}

def _handle_create_pattern(p):
    pts = tuple((float(x[0]), float(x[1]), int(x[2])) for x in p["points"])
    idx = pattern_api.CreatePatternWithPoints(pts)
    return {"success": True, "pattern_index": idx}

def _handle_set_pattern_name(p):
    result = pattern_api.SetPatternName(int(p["pattern_index"]), str(p["name"]))
    return {"success": bool(result)}

def _handle_get_line_count(p):
    return {"success": True, "line_count": pattern_api.GetLineCount(int(p["pattern_index"]))}

def _handle_add_seam(p):
    result = pattern_api.AddSeamlinePairGroup(
        int(p["pattern_a"]), int(p["line_a"]),
        int(p["pattern_b"]), int(p["line_b"]),
        bool(p.get("direction_a", True)), bool(p.get("direction_b", True)))
    return {"success": True, "seam_name": str(result) if result else None}

def _handle_add_fabric(p):
    idx = fabric_api.AddFabric(str(p["file_path"]))
    return {"success": True, "fabric_index": idx}

def _handle_assign_fabric(p):
    result = fabric_api.AssignFabricToPattern(
        int(p["fabric_index"]), int(p["pattern_index"]), int(p.get("assign_option", 1)))
    return {"success": bool(result)}

def _handle_simulate(p):
    frames = int(p.get("frames", 100))
    utility_api.Simulate(frames)
    return {"success": True, "frames": frames}

def _handle_export_obj(p):
    paths = export_api.ExportOBJ(str(p["file_path"]), _default_export_option())
    return {"success": True, "paths": _flatten(paths)}

def _handle_export_render(p):
    paths = export_api.ExportRenderingImage(
        str(p["file_path"]), bool(p.get("render_all_colorways", False)), 0)
    return {"success": True, "paths": _flatten(paths)}

def _handle_export_techpack(p):
    path = str(p["file_path"])
    export_api.ExportTechPack(path, _default_techpack_option())
    return {"success": True, "path": path}

def _handle_export_dxf(p):
    path = str(p["file_path"])
    result = export_api.ExportDXF(path, _default_dxf_option())
    return {"success": True, "path": str(result) if result else path}

def _handle_get_scene_state(p):
    pc = pattern_api.GetPatternCount()
    patterns = []
    for i in range(pc):
        patterns.append({
            "index": i, "name": pattern_api.GetPatternName(i),
            "line_count": pattern_api.GetLineCount(i),
            "fabric_index": fabric_api.GetFabricIndexForPattern(i)})
    fc = fabric_api.GetFabricCount(True)
    fabrics = [{"index": i, "name": fabric_api.GetFabricName(i)} for i in range(fc)]
    sc = pattern_api.GetSeamlinePairGroupCount()
    seams = [{"index": i, "name": pattern_api.GetSeamlinePairGroupName(i)} for i in range(sc)]
    return {"success": True, "patterns": patterns, "fabrics": fabrics, "seams": seams}

# -- V2 Handlers ----------------------------------------------------------

def _handle_export_pattern_json(p):
    tmp = os.path.join(tempfile.gettempdir(), "clo_mcp_pattern.json")
    if not export_api.ExportPatternJSON(tmp):
        return {"error": "ExportPatternJSON returned False"}
    try:
        with open(tmp, "r") as f:
            data = json.load(f)
        return {"success": True, "pattern_json": data}
    except Exception as e:
        return {"error": f"Failed to read PatternJSON: {e}"}

def _handle_get_pattern_name(p):
    idx = int(p["pattern_index"])
    return {"success": True, "name": str(pattern_api.GetPatternName(idx)), "pattern_index": idx}

def _handle_get_point_count(p):
    return {"success": True, "point_count": pattern_api.GetPointCount(
        int(p["pattern_index"]), int(p["line_index"]))}

# -- V4 Handlers ----------------------------------------------------------

def _handle_import_file(p):
    file_path = str(p["file_path"])
    result = import_api.ImportFile(file_path)
    return {"success": bool(result), "file_path": file_path}

def _handle_delete_pattern(p):
    idx = int(p["pattern_index"])
    result = pattern_api.DeletePattern(idx)
    return {"success": bool(result), "pattern_index": idx}

# -- Helpers ---------------------------------------------------------------

def _default_export_option():
    try:
        import ApiTypes
        opt = ApiTypes.ImportExportOption()
        opt.scale, opt.bSaveInZip = 1, False
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
    if obj is None: return []
    if isinstance(obj, str): return [obj]
    out = []
    for item in obj:
        if isinstance(item, (list, tuple)): out.extend(_flatten(item))
        else: out.append(str(item))
    return out

# -- Dispatch --------------------------------------------------------------

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
    "export_pattern_json": _handle_export_pattern_json,
    "get_pattern_name": _handle_get_pattern_name,
    "get_point_count": _handle_get_point_count,
    # V4
    "import_file": _handle_import_file,
    "delete_pattern": _handle_delete_pattern,
}

def handle_command(raw_json: str) -> str:
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
    try:
        return json.dumps(handler(cmd.get("params", {})))
    except Exception as e:
        return json.dumps({"error": f"{action} failed: {e}",
                           "traceback": traceback.format_exc()})

# -- TCP Server ------------------------------------------------------------

def _client_session(conn, addr):
    buf = ""
    try:
        while True:
            data = conn.recv(RECV_BUF)
            if not data: break
            buf += data.decode("utf-8")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if not line: continue
                conn.sendall((handle_command(line) + "\n").encode("utf-8"))
    except Exception:
        pass
    finally:
        try: conn.close()
        except Exception: pass

def _run_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    print(f"[CLO Bridge] Listening on {HOST}:{PORT}")
    while True:
        try:
            conn, addr = server.accept()
            print(f"[CLO Bridge] Connection from {addr}")
            threading.Thread(target=_client_session, args=(conn, addr), daemon=True).start()
        except Exception as e:
            print(f"[CLO Bridge] Accept error: {e}")

# -- Entry point -----------------------------------------------------------
threading.Thread(target=_run_server, daemon=True).start()
print("[CLO Bridge] Plugin loaded — server thread started")

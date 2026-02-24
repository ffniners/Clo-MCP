# CLO3D MCP Server (V1)

An MCP server that lets Claude control CLO3D garment design software via its Python plugin API.

## Architecture

```
Claude (MCP Client)
    ↓ tool calls (stdio)
mcp_server.py (external Python process)
    ↓ TCP socket (127.0.0.1:9876, newline-delimited JSON)
clo_bridge.py (Python plugin loaded inside CLO)
    ↓ direct function calls
CLO Python API (pattern_api, fabric_api, export_api, utility_api)
```

## Prerequisites

- CLO3D 2025.2 or later (SDK v9.1.0+)
- Python 3.10+
- `mcp` SDK (`pip install mcp`)

## Installation

### 1. Install the MCP server dependencies

```bash
cd clo3d-mcp
pip install -r requirements.txt
```

### 2. Load the bridge plugin into CLO

1. Open CLO3D.
2. Go to the **Plugin** tab in the top toolbar.
3. Click **Plugin Manager**.
4. Click **+ ADD** and browse to `clo_bridge.py`.
5. Enable the plugin checkbox — the console should print:
   ```
   [CLO Bridge] Plugin loaded — server thread started
   [CLO Bridge] Listening on 127.0.0.1:9876
   ```

The bridge is now listening for commands. It stays active for the duration of your CLO session.

### 3. Add the MCP server to Claude's config

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or the equivalent on your platform:

```json
{
  "mcpServers": {
    "clo3d": {
      "command": "python",
      "args": ["/absolute/path/to/clo3d-mcp/mcp_server.py"]
    }
  }
}
```

Restart Claude Desktop. The `clo3d` tools will appear in the tool list.

## V1 Tools

| Tool | Description |
|------|-------------|
| `ping` | Verify the bridge is alive |
| `get_pattern_count` | Number of patterns in the scene |
| `create_pattern` | Create a pattern from `[x, y, curvature]` points |
| `set_pattern_name` | Name a pattern by index |
| `get_line_count` | Number of edges on a pattern |
| `add_seam` | Sew two pattern edges together |
| `add_fabric` | Load a `.zfab` file, returns fabric index |
| `assign_fabric` | Assign a fabric to a pattern |
| `simulate` | Run cloth simulation (default 100 frames) |
| `export_obj` | Export scene as OBJ |
| `export_render` | Export rendered image |
| `export_techpack` | Export tech pack JSON |
| `export_dxf` | Export patterns as DXF |
| `get_scene_state` | JSON summary of patterns, fabrics, and seams |

## Example: Two Rectangles, Sew, Simulate, Export

This walkthrough creates two rectangular pattern pieces, sews them on one edge, runs simulation, and exports an OBJ file. You can do this by asking Claude, or by calling the tools directly.

### Step-by-step tool calls

**1. Check the bridge is running:**

```
ping
→ {"success": true, "message": "pong"}
```

**2. Create the front panel (300mm x 500mm rectangle):**

```
create_pattern(points=[[0,0,0], [0,500,0], [300,500,0], [300,0,0]])
→ {"success": true, "pattern_index": 0}
```

**3. Name it:**

```
set_pattern_name(pattern_index=0, name="Front")
→ {"success": true}
```

**4. Create the back panel (offset in X so it doesn't overlap in 2D):**

```
create_pattern(points=[[400,0,0], [400,500,0], [700,500,0], [700,0,0]])
→ {"success": true, "pattern_index": 1}
```

**5. Name it:**

```
set_pattern_name(pattern_index=1, name="Back")
→ {"success": true}
```

**6. Check edge counts to identify which lines to sew:**

```
get_line_count(pattern_index=0)
→ {"success": true, "line_count": 4}

get_line_count(pattern_index=1)
→ {"success": true, "line_count": 4}
```

For a rectangle defined as `(0,0)→(0,500)→(300,500)→(300,0)`, the lines are:
- Line 0: left edge (0,0)→(0,500)
- Line 1: top edge (0,500)→(300,500)
- Line 2: right edge (300,500)→(300,0)
- Line 3: bottom edge (300,0)→(0,0)

**7. Sew the right edge of Front (line 2) to the left edge of Back (line 0):**

```
add_seam(pattern_a=0, line_a=2, pattern_b=1, line_b=0, direction_a=true, direction_b=true)
→ {"success": true, "seam_name": "Seam 1"}
```

**8. Run simulation:**

```
simulate(frames=100)
→ {"success": true, "frames": 100}
```

**9. Export the result:**

```
export_obj(file_path="/Users/you/Desktop/garment.obj")
→ {"success": true, "paths": ["/Users/you/Desktop/garment.obj", ...]}
```

**10. Verify scene state:**

```
get_scene_state()
→ {
    "success": true,
    "patterns": [
      {"index": 0, "name": "Front", "line_count": 4, "fabric_index": 0},
      {"index": 1, "name": "Back", "line_count": 4, "fabric_index": 0}
    ],
    "fabrics": [{"index": 0, "name": "Default"}],
    "seams": [{"index": 0, "name": "Seam 1"}]
  }
```

## Communication Protocol

The MCP server sends newline-delimited JSON to the bridge over TCP:

```json
{"action": "create_pattern", "params": {"points": [[0,0,0],[0,500,0],[300,500,0],[300,0,0]]}}
```

The bridge responds with newline-delimited JSON:

```json
{"success": true, "pattern_index": 0}
```

On error:

```json
{"error": "create_pattern failed: invalid point format"}
```

## Troubleshooting

- **"Cannot connect to CLO bridge"** — Make sure CLO is running and the bridge plugin is loaded and enabled in Plugin Manager.
- **Bridge not starting** — Check CLO's Python console for errors. The plugin prints `[CLO Bridge] Listening on 127.0.0.1:9876` on successful start.
- **Port conflict** — If 9876 is in use, change `PORT` in both `clo_bridge.py` and `BRIDGE_PORT` in `mcp_server.py`.

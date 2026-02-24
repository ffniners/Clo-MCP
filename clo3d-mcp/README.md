# CLO3D MCP Server

An MCP server that lets Claude control CLO3D garment design software via its Python plugin API.

**V1** provides raw API access with explicit pattern/line indices.
**V2** adds a semantic layer — named pieces, automatic edge classification, and garment type definitions that let Claude describe garments naturally.

## Architecture

```
Claude (MCP Client)
    ↓ tool calls (stdio)
mcp_server.py (external Python process)
    ├── V1: raw bridge calls
    └── V2: semantic layer (geometry resolver, state manager, seam planner)
    ↓ TCP socket (127.0.0.1:9876, newline-delimited JSON)
clo_bridge.py (Python plugin loaded inside CLO)
    ↓ direct function calls
CLO Python API (pattern_api, fabric_api, export_api, utility_api)
```

### V2 Semantic Layer

```
mcp_server.py
    ↓
semantic/
    geometry.py       ← classifies edges by position/length/curvature
    state_manager.py  ← persists patterns, fabrics, seams to JSON
    seam_planner.py   ← maps named edges to line indices, validates lengths
    garment_types.py  ← T-shirt definition + measurement→coordinate derivation
```

## Prerequisites

- CLO3D 2025.2 or later (SDK v9.1.0+)
- Python 3.10+
- `mcp` SDK (`pip install mcp`)

## Installation

### 1. Install dependencies

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

### 3. Add the MCP server to Claude's config

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or equivalent:

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

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLO_MCP_STATE_PATH` | `./state/garment_state.json` | Path to the garment state file |
| `CLO_MCP_SEAM_TOLERANCE` | `0.05` (5%) | Max allowed edge length mismatch for seam validation |

## V1 Tools

| Tool | Description |
|------|-------------|
| `ping` | Verify the bridge is alive |
| `get_pattern_count` | Number of patterns in the scene |
| `create_pattern` | Create a pattern from `[x, y, curvature]` points |
| `set_pattern_name` | Name a pattern by index |
| `get_line_count` | Number of edges on a pattern |
| `add_seam` | Sew two pattern edges (raw indices) |
| `add_fabric` | Load a `.zfab` file, returns fabric index |
| `assign_fabric` | Assign fabric to pattern (raw indices) |
| `simulate` | Run cloth simulation (default 100 frames) |
| `export_obj` | Export scene as OBJ |
| `export_render` | Export rendered image |
| `export_techpack` | Export tech pack JSON |
| `export_dxf` | Export patterns as DXF |
| `get_scene_state` | JSON summary of CLO scene |

## V2 Tools — Semantic Layer

| Tool | Description |
|------|-------------|
| `create_piece` | Create a named pattern piece, auto-classify edges, register in state |
| `sew_pieces` | Sew two named pieces by edge label (e.g. "left", "top") |
| `sew_garment` | Execute full seam plan for a garment type in one call |
| `get_garment_state` | Full state JSON: patterns with edge labels, fabrics, seams |
| `load_state` | Reload state from disk and re-sync with CLO |
| `clear_state` | Wipe state file (does not modify CLO scene) |
| `add_fabric_named` | Load `.zfab` and register with a friendly name |
| `assign_fabric_to_piece` | Assign named fabric to named piece |
| `build_tshirt` | **Compound tool**: create T-shirt from measurements, sew, simulate |

## Geometry Resolver

The geometry resolver is the core of V2. It classifies each pattern edge by:

| Label | Rule |
|-------|------|
| `top` | Highest average Y coordinate |
| `bottom` | Lowest average Y coordinate |
| `left` | Lowest average X coordinate |
| `right` | Highest average X coordinate |
| `curved` | Contains bezier/curve points (curvature != 0) |
| `longest` | Greatest arc length |
| `shortest` | Smallest arc length |
| `top_left` | Top-region edge with lowest X (extended) |
| `top_right` | Top-region edge with highest X (extended) |
| `bottom_left` | Bottom-region edge with lowest X (extended) |
| `bottom_right` | Bottom-region edge with highest X (extended) |

### Debugging Edge Misclassification

If seams connect wrong edges:

1. Call `get_garment_state` and check the `edges` dict for each pattern
2. Look at `pattern_json_snapshot.creation_points` to see the actual coordinates
3. The `warnings` field flags ambiguous cases (e.g. two edges with identical length)
4. The state file at `./state/garment_state.json` contains all data for inspection

## T-Shirt Measurements

The `build_tshirt` tool accepts these measurements (all in mm):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `chest_width_mm` | 500 | Full front panel width |
| `body_length_mm` | 700 | Shoulder to hem |
| `shoulder_width_mm` | 420 | Shoulder point to shoulder point |
| `sleeve_length_mm` | 220 | Shoulder to sleeve hem |
| `sleeve_width_mm` | 180 | Sleeve opening width at shoulder |
| `neck_drop_mm` | 80 | Front neckline drop below shoulder |
| `fabric_path` | (none) | Optional path to `.zfab` file |
| `simulate_frames` | 100 | Simulation frame count |

### Derivation Formulas

All formulas are documented in `semantic/garment_types.py`:

- **Front bodice**: 6-point shape — `chest_width_mm` wide, `body_length_mm` tall, with bezier neck opening derived from `neck_drop_mm` and `shoulder_width_mm`
- **Back bodice**: Same as front but with shallower neck drop (40% of front), offset in 2D
- **Sleeves**: Rectangles — `sleeve_width_mm` × `sleeve_length_mm`, placed below bodice panels

## State File Schema

```json
{
  "version": 2,
  "patterns": {
    "0": {
      "index": 0,
      "name": "Front_Bodice",
      "role": "front_bodice",
      "edges": {
        "top": 1, "bottom": 5, "left": 0, "right": 4,
        "curved": 2, "longest": 0, "shortest": 2,
        "top_left": 1, "top_right": 3
      },
      "fabric_index": 0,
      "pattern_json_snapshot": {
        "creation_points": [[0,0,0], [0,700,0], ...]
      }
    }
  },
  "fabrics": {
    "0": {
      "index": 0,
      "name": "Cotton_Oxford",
      "path": "/path/to/fabric.zfab"
    }
  },
  "seams": [
    {
      "group_name": "left_side_seam",
      "patternA": "Front_Bodice",
      "edgeA": "left",
      "patternB": "Back_Bodice",
      "edgeB": "right"
    }
  ],
  "colorways": []
}
```

## Examples

### Example 1: Build T-Shirt (Single Command)

```
build_tshirt(
    chest_width_mm=520,
    body_length_mm=720,
    shoulder_width_mm=440,
    sleeve_length_mm=200,
    sleeve_width_mm=190,
    neck_drop_mm=85,
    fabric_path="/path/to/cotton.zfab",
    simulate_frames=150
)
```

This single call:
1. Creates 4 pattern pieces (front bodice, back bodice, left sleeve, right sleeve)
2. Classifies all edges automatically
3. Loads the fabric and assigns it to all pieces
4. Sews all 6 seams (2 side seams, 4 shoulder seams)
5. Runs 150 frames of simulation
6. Returns full state summary

### Example 2: Build T-Shirt, Then Export

```
# Step 1: Build
build_tshirt(chest_width_mm=500, body_length_mm=700)

# Step 2: Export render
export_render(file_path="/Users/you/Desktop/tshirt_render.png")

# Step 3: Export DXF for cutting
export_dxf(file_path="/Users/you/Desktop/tshirt_patterns.dxf")

# Step 4: Export tech pack
export_techpack(file_path="/Users/you/Desktop/tshirt_techpack.json")
```

### Example 3: Step-by-Step with V2 Semantic Tools

```
# Create pieces individually
create_piece(name="Front", points=[[0,0,0],[0,500,0],[300,500,0],[300,0,0]], role="front_bodice")
create_piece(name="Back", points=[[400,0,0],[400,500,0],[700,500,0],[700,0,0]], role="back_bodice")

# Check what edges were classified
get_garment_state()

# Sew by edge name
sew_pieces(pattern_a_name="Front", edge_a="right", pattern_b_name="Back", edge_b="left")

# Simulate
simulate(frames=100)

# Export
export_obj(file_path="/Users/you/Desktop/garment.obj")
```

### Example 4: V1 Raw Access (Still Works)

```
create_pattern(points=[[0,0,0], [0,500,0], [300,500,0], [300,0,0]])
set_pattern_name(pattern_index=0, name="Front")
add_seam(pattern_a=0, line_a=2, pattern_b=1, line_b=0)
simulate(frames=100)
export_obj(file_path="/Users/you/Desktop/garment.obj")
```

## Running Tests

```bash
cd clo3d-mcp
pip install pytest
python -m pytest tests/ -v
```

The geometry resolver has 43 unit tests covering:
- Edge classification for rectangles, squares, triangles, pentagons
- Curved edge detection
- Ambiguity warnings
- Extended classification (top_left, top_right, etc.)
- Edge length comparison (used by seam planner)
- Determinism / stability

## Troubleshooting

- **"Cannot connect to CLO bridge"** — Make sure CLO is running and the bridge plugin is loaded in Plugin Manager.
- **"Pattern not found in state"** — Use `load_state` to re-sync after CLO restart, or `get_garment_state` to see current state.
- **Wrong edges being sewn** — Check `get_garment_state`, look at the `edges` dict. Compare with `pattern_json_snapshot.creation_points`. Adjust seam edge labels accordingly.
- **Port conflict** — Change `PORT` in `clo_bridge.py` and `BRIDGE_PORT` in `mcp_server.py`.
- **State file location** — Set `CLO_MCP_STATE_PATH` env var to customize.

# CLO3D MCP Server

An MCP server that lets Claude control CLO3D garment design software via its Python plugin API.

**V1** provides raw API access with explicit pattern/line indices.
**V2** adds a semantic layer — named pieces, automatic edge classification, and garment type definitions that let Claude describe garments naturally.
**V3** adds authoritative geometry classification, real seam length validation, transactional builds, garment extensibility, atomic state persistence, and protocol observability.
**V4** adds parametric design modifications, curved sleeve caps and armholes, CLO file import, and garment validation.

## V4 Highlights

- **Parametric design modifications**: Modify individual measurements and rebuild garments with `modify_measurement`, `get_current_measurements`, and `resize_garment`. The full pipeline (delete old patterns, re-derive, re-create, re-sew, re-apply fabric) runs automatically.
- **Curved sleeve caps and armholes**: T-shirt sleeves now use a 5-point bezier sleeve cap instead of a flat rectangle. Bodice pieces have 8-point shapes with armhole cutouts. Sleeve cap arc length is designed to match armhole arc length.
- **Import from CLO files**: `import_garment` opens a `.zprj`/`.zpac` file in CLO, scans all patterns, classifies edges, and registers them in state. Supports optional role mapping by garment type.
- **Garment validation**: `validate_garment` runs pre-flight checks (seam completeness, duplicate seams, edge length mismatches, fabric assignment, orphan pieces, pattern count) and returns a structured report.
- **State version 4**: Adds `measurements` storage. Automatic migration from V2 and V3 state files.
- **Test coverage**: 166 tests covering all features.

### Migration from V3

- **State file**: V3 state files are automatically migrated to V4 on first load. The migration adds the `measurements` key.
- **Tools**: All V1/V2/V3 tools remain available. No breaking changes.
- **Geometry change**: T-shirt derivation now produces curved sleeves (5 points) and armhole bodice (8 points). The seam plan uses `curved_0`/`curved_1` labels for sleeve cap edges.
- **build_tshirt**: Now stores measurements in state for later parametric modifications.

## Architecture

```
Claude (MCP Client)
    ↓ tool calls (stdio)
mcp_server.py (external Python process)
    ├── V1: raw bridge calls
    ├── V2: semantic layer (geometry resolver, state manager, seam planner)
    ├── V3: reclassification, health, transactional builds
    └── V4: parametric modification, import, validation
    ↓ TCP socket (127.0.0.1:9876, newline-delimited JSON)
clo_bridge.py (Python plugin loaded inside CLO)
    ↓ direct function calls
CLO Python API (pattern_api, fabric_api, export_api, import_api, utility_api)
```

### Semantic Layer

```
mcp_server.py
    ↓
semantic/
    geometry.py       ← classifies edges by position/length/curvature
    state_manager.py  ← persists patterns, fabrics, seams, measurements to JSON (atomic writes)
    seam_planner.py   ← maps named edges to line indices, validates lengths (warn/strict)
    garment_types.py  ← garment definitions + measurement→coordinate derivation + spec loading
    validator.py      ← pre-flight garment validation checks (V4)
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
| `CLO_MCP_SEAM_MODE` | `warn` | Seam validation mode: `warn` (log warning, proceed) or `strict` (block seam creation) |

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

## V3 Tools

| Tool | Description |
|------|-------------|
| `reclassify_piece` | Re-derive edge labels for a pattern piece after manual CLO edits |
| `reclassify_all` | Reclassify edge labels for all registered pattern pieces |
| `health` | Report server version, bridge connectivity, capabilities, and seam mode |

## V4 Tools

| Tool | Description |
|------|-------------|
| `get_current_measurements` | Return stored measurements for the current garment |
| `modify_measurement` | Update a single measurement value (does not rebuild) |
| `resize_garment` | Rebuild garment from stored measurements: delete old patterns, re-derive, re-create, re-sew, re-apply fabric |
| `import_garment` | Import a CLO file, scan patterns, classify edges, register in state |
| `validate_garment` | Pre-flight validation: seam completeness, duplicates, edge lengths, fabric, orphan pieces |

## Geometry Resolver

The geometry resolver is the core of V2/V3. It classifies each pattern edge by:

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

### Reclassification (V3)

After manually editing a pattern in CLO, edge labels may become stale. Use:
- `reclassify_piece(pattern_name="Front_Bodice")` — reclassify one piece
- `reclassify_all()` — reclassify all registered pieces

Reclassification first tries to fetch PatternJSON from CLO via the bridge (authoritative after edits), then falls back to the stored creation points snapshot.

### Debugging Edge Misclassification

If seams connect wrong edges:

1. Call `get_garment_state` and check the `edges` dict for each pattern
2. Look at `pattern_json_snapshot.creation_points` to see the actual coordinates
3. The `warnings` field flags ambiguous cases (e.g. two edges with identical length)
4. Use `reclassify_piece` or `reclassify_all` after manual edits
5. The state file at `./state/garment_state.json` contains all data for inspection

## Seam Validation (V3)

Seam validation checks that the edges being sewn have compatible lengths. Two modes:

| Mode | Env Var | Behavior |
|------|---------|----------|
| `warn` (default) | `CLO_MCP_SEAM_MODE=warn` | Warns about length mismatch but allows seam creation |
| `strict` | `CLO_MCP_SEAM_MODE=strict` | Blocks seam creation when mismatch exceeds tolerance |

Tolerance is configurable via `CLO_MCP_SEAM_TOLERANCE` (default 0.05 = 5%).

Length data comes from stored `edge_geometry` in state (V3), falling back to creation points if geometry is unavailable.

## Garment Types

### Built-in

| Type | Pieces | Seams |
|------|--------|-------|
| `t_shirt` | front_bodice, back_bodice, sleeve_left, sleeve_right | 6 (2 side, 4 shoulder) |
| `a_line_skirt` | front_panel, back_panel | 2 (side seams) |

### Custom Garment Specs (V3)

Garment types can be loaded from JSON spec files in the `garment_specs/` directory:

```json
{
  "name": "garment_name",
  "pieces": [
    {"role": "piece_role", "description": "Description"}
  ],
  "seam_plan": [
    {
      "pattern_a": "role_a", "edge_a": "edge_label",
      "pattern_b": "role_b", "edge_b": "edge_label",
      "label": "seam_name", "flip": false
    }
  ],
  "default_measurements": {"key_mm": 100.0}
}
```

Load at runtime:
```python
from semantic.garment_types import load_garment_from_spec, register_garment_type
gt = load_garment_from_spec("garment_specs/my_garment.json")
register_garment_type(gt, derivation_fn=my_derive_function)
```

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

### Derivation Formulas (V4)

All formulas are documented in `semantic/garment_types.py`:

- **Front bodice**: 8-point shape with armhole cutouts — `chest_width_mm` wide, `body_length_mm` tall, bezier neck opening, and bezier armhole curves. Armhole depth = `sleeve_width_mm * 0.5`.
- **Back bodice**: Same as front but with shallower neck drop (40% of front), offset in 2D.
- **Sleeves**: 5-point shapes with curved bezier sleeve cap — `sleeve_width_mm` wide, `sleeve_length_mm` tall. Cap height = `sleeve_width_mm * 0.3`. Two curved edges (`curved_0`, `curved_1`) form the cap and are sewn to the bodice armholes.

## State File Schema (V4)

```json
{
  "version": 4,
  "revision": 42,
  "updated_at": 1709000000.0,
  "patterns": {
    "0": {
      "index": 0,
      "name": "Front_Bodice",
      "role": "front_bodice",
      "edges": {
        "top": 1, "bottom": 7, "left": 0, "right": 6,
        "curved": 2, "curved_0": 1, "curved_1": 2,
        "top_left": 1, "top_right": 5
      },
      "fabric_index": 0,
      "pattern_json_snapshot": {
        "creation_points": [[0,0,0], [0,610,0], ...]
      },
      "edge_geometry": {
        "top_left": {"line_index": 1, "arc_length": 90.0, "is_curved": true, "points": [...]},
        "left": {"line_index": 0, "arc_length": 610.0, "is_curved": false, "points": [...]}
      }
    }
  },
  "fabrics": {
    "0": {"index": 0, "name": "Cotton_Oxford", "path": "/path/to/fabric.zfab"}
  },
  "seams": [
    {"group_name": "left_side_seam", "patternA": "Front_Bodice", "edgeA": "left", "patternB": "Back_Bodice", "edgeB": "right"}
  ],
  "colorways": [],
  "measurements": {
    "garment_type": "t_shirt",
    "values": {
      "chest_width_mm": 500,
      "body_length_mm": 700,
      "shoulder_width_mm": 420,
      "sleeve_length_mm": 220,
      "sleeve_width_mm": 180,
      "neck_drop_mm": 80
    }
  }
}
```

### Response Envelope

V3+ compound tools (`build_tshirt`, `health`, `validate_garment`, `import_garment`, `resize_garment`, etc.) return a normalized response envelope:

```json
{
  "success": true,
  "correlation_id": "uuid-v4",
  "server_version": "4.0.0",
  "timestamp": 1709000000.0,
  "data": { ... },
  "warnings": ["..."],
  "error": null,
  "error_code": null
}
```

### Error Codes

| Code | Description |
|------|-------------|
| `BRIDGE_UNAVAILABLE` | Cannot connect to CLO bridge |
| `BRIDGE_TIMEOUT` | Bridge response timed out |
| `BRIDGE_ERROR` | General bridge communication error |
| `PATTERN_NOT_FOUND` | Pattern not found in state |
| `EDGE_NOT_FOUND` | Edge label not found on pattern |
| `GARMENT_UNKNOWN` | Unknown garment type |
| `VALIDATION_FAILED` | Seam validation failed (strict mode) |
| `STAGE_FAILED` | A build stage failed |

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
6. Returns structured per-stage results

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

### Example 5: Reclassify After Manual Edit (V3)

```
# After editing a pattern in CLO's UI...
reclassify_piece(pattern_name="Front_Bodice")

# Or reclassify everything
reclassify_all()

# Then check the updated edges
get_garment_state()
```

### Example 6: Check Server Health (V3)

```
health()
# Returns: server version, bridge status, seam mode, registered garment types, etc.
```

### Example 7: Modify Measurement and Resize (V4)

```
# Step 1: Build initial T-shirt
build_tshirt(chest_width_mm=500, body_length_mm=700)

# Step 2: Check current measurements
get_current_measurements()

# Step 3: Make the chest wider
modify_measurement(key="chest_width_mm", value=550)

# Step 4: Rebuild with updated measurements
resize_garment()
# Deletes old patterns, re-derives all pieces, re-creates, re-sews
```

### Example 8: Import and Validate (V4)

```
# Step 1: Import an existing CLO project
import_garment(file_path="/path/to/design.zprj", garment_type="t_shirt")
# Scans patterns, classifies edges, maps roles by name

# Step 2: Validate the imported garment
validate_garment(garment_type="t_shirt")
# Returns: {valid: true/false, errors: [...], warnings: [...], checks_passed: [...]}
```

## Running Tests

```bash
cd clo3d-mcp
pip install pytest
python -m pytest tests/ -v
```

The test suite includes 166 tests covering:
- **Geometry resolver** (54 tests): edge classification, ambiguity, extended labels, determinism, V4 sleeve cap and armhole bodice shapes
- **State manager** (41 tests): persistence, atomic writes, V2/V3/V4 migration, measurements, bulk operations, accessors, mutations
- **Seam planner** (14 tests): warn mode, strict mode, tolerance, fallback, plan execution
- **Garment types** (27 tests): derivation (curved sleeves, armholes), registry, spec loading, A-line skirt
- **Validator** (12 tests): seam completeness, duplicates, edge lengths, fabric, orphan pieces, pattern count
- **MCP tools** (12 tests): create_piece, reclassify, build_tshirt stages, health endpoint
- **Integration** (6 tests): end-to-end flows via fake TCP bridge socket

## Troubleshooting

- **"Cannot connect to CLO bridge"** — Make sure CLO is running and the bridge plugin is loaded in Plugin Manager.
- **"Pattern not found in state"** — Use `load_state` to re-sync after CLO restart, or `get_garment_state` to see current state.
- **Wrong edges being sewn** — Check `get_garment_state`, look at the `edges` dict. Use `reclassify_piece` after manual edits. Compare with `pattern_json_snapshot.creation_points`. Adjust seam edge labels accordingly.
- **Seam blocked in strict mode** — Set `CLO_MCP_SEAM_MODE=warn` or adjust `CLO_MCP_SEAM_TOLERANCE`.
- **Port conflict** — Change `PORT` in `clo_bridge.py` and `BRIDGE_PORT` in `mcp_server.py`.
- **State file location** — Set `CLO_MCP_STATE_PATH` env var to customize.
- **State migration** — V2 and V3 state files are automatically migrated to V4 on first load. No manual action needed.
- **"No measurements stored"** — Use `build_tshirt` first to create a garment with measurements before using `modify_measurement` or `resize_garment`.
- **Import finds no patterns** — Check that the CLO file is valid and contains pattern pieces. Try opening it manually in CLO first.

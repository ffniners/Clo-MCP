"""
Garment type definitions — pattern pieces, measurement-to-coordinate
derivation, and seam plans for supported garment types.

V2 implements: TSHIRT
V3 additions:
  - Spec file loading from JSON/YAML
  - Optional Python hook modules for advanced derivation formulas
  - Sample A-line skirt garment spec
  - Backward-compatible registry

Every derivation formula is commented inline so it can be corrected
after testing against real CLO PatternJSON output.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PieceDefinition:
    """Defines a pattern piece within a garment type."""
    role: str            # e.g. "front_bodice", "sleeve_left"
    description: str     # Human-readable description


@dataclass
class SeamDefinition:
    """Defines a seam between two pattern piece edges."""
    pattern_a: str       # Role name of pattern A
    edge_a: str          # Edge label on pattern A
    pattern_b: str       # Role name of pattern B
    edge_b: str          # Edge label on pattern B
    label: str = ""      # Human-readable seam name
    flip: bool = False   # Whether to flip directionB


@dataclass
class GarmentType:
    """Complete garment type definition."""
    name: str
    pieces: list[PieceDefinition]
    seam_plan: list[SeamDefinition]
    default_measurements: dict[str, float] = field(default_factory=dict)
    derivation_hook: str | None = None  # Python module path for derive fn


# =========================================================================
# T-SHIRT DEFINITION
# =========================================================================

TSHIRT = GarmentType(
    name="t_shirt",
    pieces=[
        PieceDefinition(role="front_bodice", description="Front body panel"),
        PieceDefinition(role="back_bodice", description="Back body panel"),
        PieceDefinition(role="sleeve_left", description="Left sleeve"),
        PieceDefinition(role="sleeve_right", description="Right sleeve"),
    ],
    seam_plan=[
        # Side seams — front left edge to back right edge (and vice versa)
        SeamDefinition("front_bodice", "left", "back_bodice", "right",
                       label="left_side_seam"),
        SeamDefinition("front_bodice", "right", "back_bodice", "left",
                       label="right_side_seam"),
        # Shoulder seams — front top edges to sleeve bottom edges
        SeamDefinition("front_bodice", "top_left", "sleeve_left", "bottom",
                       label="left_shoulder_front"),
        SeamDefinition("front_bodice", "top_right", "sleeve_right", "bottom",
                       label="right_shoulder_front"),
        # Back shoulder seams
        SeamDefinition("back_bodice", "top_left", "sleeve_left", "top",
                       label="left_shoulder_back", flip=True),
        SeamDefinition("back_bodice", "top_right", "sleeve_right", "top",
                       label="right_shoulder_back", flip=True),
    ],
)


# =========================================================================
# A-LINE SKIRT DEFINITION (V3 sample)
# =========================================================================

ALINE_SKIRT = GarmentType(
    name="a_line_skirt",
    pieces=[
        PieceDefinition(role="front_panel", description="Front skirt panel"),
        PieceDefinition(role="back_panel", description="Back skirt panel"),
    ],
    seam_plan=[
        SeamDefinition("front_panel", "left", "back_panel", "right",
                       label="left_side_seam"),
        SeamDefinition("front_panel", "right", "back_panel", "left",
                       label="right_side_seam"),
    ],
    default_measurements={
        "waist_width_mm": 380,
        "hem_width_mm": 550,
        "skirt_length_mm": 600,
    },
)


# =========================================================================
# Measurement → Coordinate Derivation
# =========================================================================

# Default T-shirt measurements (mm) — adult medium
DEFAULT_TSHIRT_MEASUREMENTS = {
    "chest_width_mm": 500,       # Half-chest measurement × 2 (full front panel width)
    "body_length_mm": 700,       # Shoulder to hem
    "shoulder_width_mm": 420,    # Shoulder point to shoulder point
    "sleeve_length_mm": 220,     # Shoulder point to sleeve hem
    "sleeve_width_mm": 180,      # Sleeve opening width at shoulder
    "neck_drop_mm": 80,          # How far below shoulder the neckline drops
}


def derive_tshirt_pieces(measurements: dict) -> dict[str, list[list[float]]]:
    """
    Derive pattern piece point coordinates from T-shirt measurements.

    Returns a dict of {role: [[x, y, curvature], ...]} for each piece.

    All coordinates are in mm. Pieces are laid out in 2D space with
    gaps between them to avoid overlap.

    Coordinate convention:
      - X increases to the right
      - Y increases upward
      - Origin (0,0) is at the bottom-left of the front bodice

    Each derivation formula is documented inline.
    """
    m = {**DEFAULT_TSHIRT_MEASUREMENTS, **measurements}

    chest_w = float(m["chest_width_mm"])
    body_l = float(m["body_length_mm"])
    shoulder_w = float(m["shoulder_width_mm"])
    sleeve_l = float(m["sleeve_length_mm"])
    sleeve_w = float(m["sleeve_width_mm"])
    neck_drop = float(m["neck_drop_mm"])

    # =====================================================================
    # FRONT BODICE
    # =====================================================================
    neck_w = chest_w - shoulder_w
    neck_half = neck_w / 2.0
    center_x = chest_w / 2.0

    front_bodice = [
        [0.0, 0.0, 0],                                    # P0: bottom-left
        [0.0, body_l, 0],                                  # P1: top-left (shoulder)
        [center_x - neck_half, body_l - neck_drop, 3],     # P2: neck-left (bezier curve)
        [center_x + neck_half, body_l - neck_drop, 3],     # P3: neck-right (bezier curve)
        [chest_w, body_l, 0],                              # P4: top-right (shoulder)
        [chest_w, 0.0, 0],                                 # P5: bottom-right
    ]

    # =====================================================================
    # BACK BODICE
    # =====================================================================
    back_neck_drop = neck_drop * 0.4
    bx = chest_w + 100.0

    back_bodice = [
        [bx, 0.0, 0],                                          # P0: bottom-left
        [bx, body_l, 0],                                       # P1: top-left (shoulder)
        [bx + center_x - neck_half, body_l - back_neck_drop, 3],  # P2: neck-left
        [bx + center_x + neck_half, body_l - back_neck_drop, 3],  # P3: neck-right
        [bx + chest_w, body_l, 0],                              # P4: top-right (shoulder)
        [bx + chest_w, 0.0, 0],                                 # P5: bottom-right
    ]

    # =====================================================================
    # LEFT SLEEVE
    # =====================================================================
    sx_l = 0.0
    sy = -sleeve_l - 100.0

    sleeve_left = [
        [sx_l, sy, 0],                       # P0: bottom-left (cuff)
        [sx_l, sy + sleeve_l, 0],            # P1: top-left (armhole side)
        [sx_l + sleeve_w, sy + sleeve_l, 0], # P2: top-right (armhole side)
        [sx_l + sleeve_w, sy, 0],            # P3: bottom-right (cuff)
    ]

    # =====================================================================
    # RIGHT SLEEVE
    # =====================================================================
    sx_r = sleeve_w + 100.0

    sleeve_right = [
        [sx_r, sy, 0],                       # P0: bottom-left (cuff)
        [sx_r, sy + sleeve_l, 0],            # P1: top-left (armhole side)
        [sx_r + sleeve_w, sy + sleeve_l, 0], # P2: top-right (armhole side)
        [sx_r + sleeve_w, sy, 0],            # P3: bottom-right (cuff)
    ]

    return {
        "front_bodice": front_bodice,
        "back_bodice": back_bodice,
        "sleeve_left": sleeve_left,
        "sleeve_right": sleeve_right,
    }


def derive_aline_skirt_pieces(measurements: dict) -> dict[str, list[list[float]]]:
    """
    Derive pattern piece coordinates from A-line skirt measurements.

    Returns {role: [[x, y, curvature], ...]} for front_panel and back_panel.
    """
    m = {**ALINE_SKIRT.default_measurements, **measurements}

    waist_w = float(m["waist_width_mm"])
    hem_w = float(m["hem_width_mm"])
    length = float(m["skirt_length_mm"])

    # Front panel: trapezoid — wider at hem than waist
    waist_inset = (hem_w - waist_w) / 2.0

    front_panel = [
        [0.0, 0.0, 0],                  # P0: bottom-left (hem)
        [waist_inset, length, 0],        # P1: top-left (waist)
        [waist_inset + waist_w, length, 0],  # P2: top-right (waist)
        [hem_w, 0.0, 0],                # P3: bottom-right (hem)
    ]

    # Back panel: same shape, offset to the right
    bx = hem_w + 100.0
    back_panel = [
        [bx, 0.0, 0],
        [bx + waist_inset, length, 0],
        [bx + waist_inset + waist_w, length, 0],
        [bx + hem_w, 0.0, 0],
    ]

    return {
        "front_panel": front_panel,
        "back_panel": back_panel,
    }


# Registry of derivation functions keyed by garment name
_DERIVATION_FUNCTIONS = {
    "t_shirt": derive_tshirt_pieces,
    "a_line_skirt": derive_aline_skirt_pieces,
}


# =========================================================================
# Spec file loading (V3)
# =========================================================================

def load_garment_from_spec(spec_path: str) -> GarmentType:
    """
    Load a garment type definition from a JSON spec file.

    Spec file format:
    {
        "name": "garment_name",
        "pieces": [
            {"role": "piece_role", "description": "..."}
        ],
        "seam_plan": [
            {
                "pattern_a": "role_a", "edge_a": "edge_label",
                "pattern_b": "role_b", "edge_b": "edge_label",
                "label": "seam_name", "flip": false
            }
        ],
        "default_measurements": {"key_mm": 100.0},
        "derivation_hook": "module.path"  // optional
    }
    """
    with open(spec_path, "r") as f:
        data = json.load(f)

    pieces = [
        PieceDefinition(role=p["role"], description=p.get("description", ""))
        for p in data.get("pieces", [])
    ]

    seam_plan = [
        SeamDefinition(
            pattern_a=s["pattern_a"],
            edge_a=s["edge_a"],
            pattern_b=s["pattern_b"],
            edge_b=s["edge_b"],
            label=s.get("label", ""),
            flip=s.get("flip", False),
        )
        for s in data.get("seam_plan", [])
    ]

    return GarmentType(
        name=data["name"],
        pieces=pieces,
        seam_plan=seam_plan,
        default_measurements=data.get("default_measurements", {}),
        derivation_hook=data.get("derivation_hook"),
    )


def load_garment_specs_from_dir(specs_dir: str) -> list[GarmentType]:
    """Load all .json garment specs from a directory."""
    loaded = []
    if not os.path.isdir(specs_dir):
        return loaded
    for fname in sorted(os.listdir(specs_dir)):
        if fname.endswith(".json"):
            try:
                gt = load_garment_from_spec(os.path.join(specs_dir, fname))
                loaded.append(gt)
            except (json.JSONDecodeError, KeyError, FileNotFoundError):
                pass
    return loaded


def get_derivation_function(garment_name: str):
    """Get the derivation function for a garment type, if one exists."""
    return _DERIVATION_FUNCTIONS.get(garment_name)


# =========================================================================
# Registry
# =========================================================================

GARMENT_REGISTRY: dict[str, GarmentType] = {
    "t_shirt": TSHIRT,
    "a_line_skirt": ALINE_SKIRT,
}


def register_garment_type(gt: GarmentType, derivation_fn=None) -> None:
    """Register a garment type (and optional derivation function) at runtime."""
    GARMENT_REGISTRY[gt.name] = gt
    if derivation_fn is not None:
        _DERIVATION_FUNCTIONS[gt.name] = derivation_fn


def get_garment_type(name: str) -> GarmentType | None:
    """Look up a garment type by name."""
    return GARMENT_REGISTRY.get(name)


def list_garment_types() -> list[str]:
    """Return all registered garment type names."""
    return list(GARMENT_REGISTRY.keys())

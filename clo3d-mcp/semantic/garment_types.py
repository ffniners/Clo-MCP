"""
Garment type definitions — pattern pieces, measurement-to-coordinate
derivation, and seam plans for supported garment types.

V2 implements: TSHIRT

Every derivation formula is commented inline so it can be corrected
after testing against real CLO PatternJSON output.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
    # Shape: trapezoid-like rectangle with neck cutout
    #
    # The front bodice is chest_w wide and body_l tall.
    # The top edge is split by a neck opening.
    #
    #   P4---P3        P2---P1
    #   |     \       /     |
    #   |      P5---P6      |      (neck curve, dropped by neck_drop)
    #   |                   |
    #   P0-----------------P7       (hem line)
    #
    # However, for V2 we use a simplified 6-point shape:
    # Bottom-left, top-left shoulder, neck-left, neck-right,
    # top-right shoulder, bottom-right
    #
    # half_chest = chest_w / 2   (from center)
    # shoulder_inset = (chest_w - shoulder_w) / 2  (how far shoulder is from side)
    # neck_half = (chest_w - shoulder_w) / 2 + some offset... simplified:

    # For a standard t-shirt, the neck opening is roughly:
    #   neck_width = chest_w - shoulder_w
    # This is the gap between the two shoulder points at the top.

    neck_w = chest_w - shoulder_w
    # Neck half-width from center
    neck_half = neck_w / 2.0
    # Center X of the front bodice
    center_x = chest_w / 2.0

    # Points defined CCW from bottom-left:
    # P0: bottom-left (hem)
    # P1: top-left (shoulder point)
    # P2: neck-left (where neck begins, dropped from shoulder)
    # P3: neck-right (symmetric)
    # P4: top-right (shoulder point)
    # P5: bottom-right (hem)

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
    # Same shape as front but offset in X to avoid 2D overlap.
    # Back neck drop is typically shallower (less drop).
    #
    # back_neck_drop = neck_drop * 0.4 (backs have higher neckline)

    back_neck_drop = neck_drop * 0.4
    # Offset back bodice to the right by chest_w + 100mm gap
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
    # Simplified sleeve: rectangle with sleeve_w width and sleeve_l height.
    # The top edge (shoulder side) will be sewn to the bodice.
    # Placed below the bodice in 2D.
    #
    # sleeve_cap_height = sleeve_w * 0.3 (how much taller the cap is
    #   vs the underarm)
    #
    # For V2 simplicity, sleeves are rectangles:
    #   Width = sleeve_w, Height = sleeve_l
    #   The "bottom" edge (at higher Y, since it sews to shoulder)
    #   corresponds to the armhole.

    sx_l = 0.0        # Left sleeve X origin
    sy = -sleeve_l - 100.0   # Below the bodice with 100mm gap

    sleeve_left = [
        [sx_l, sy, 0],                       # P0: bottom-left (cuff)
        [sx_l, sy + sleeve_l, 0],            # P1: top-left (armhole side)
        [sx_l + sleeve_w, sy + sleeve_l, 0], # P2: top-right (armhole side)
        [sx_l + sleeve_w, sy, 0],            # P3: bottom-right (cuff)
    ]

    # =====================================================================
    # RIGHT SLEEVE
    # =====================================================================
    # Mirror of left sleeve, offset to the right

    sx_r = sleeve_w + 100.0   # Right sleeve offset

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


# =========================================================================
# Registry
# =========================================================================

GARMENT_REGISTRY: dict[str, GarmentType] = {
    "t_shirt": TSHIRT,
}


def get_garment_type(name: str) -> GarmentType | None:
    """Look up a garment type by name."""
    return GARMENT_REGISTRY.get(name)


def list_garment_types() -> list[str]:
    """Return all registered garment type names."""
    return list(GARMENT_REGISTRY.keys())

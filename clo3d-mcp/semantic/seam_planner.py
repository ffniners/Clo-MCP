"""
Seam Planner — translates semantic seam descriptions into CLO API calls.

Maps (patternA_name, edgeA_label, patternB_name, edgeB_label) into
AddSeamlinePairGroup(patternA_index, lineA_index, patternB_index, lineB_index,
                     directionA, directionB).

Validates:
  - Both patterns exist in state
  - Both edges exist in state
  - Edge lengths are within tolerance (configurable via CLO_MCP_SEAM_TOLERANCE)

V3 additions:
  - Configurable seam validation mode:
    - "warn" (default, backward compatible): warns but does not block
    - "strict": blocks seam creation when mismatch exceeds tolerance
  - Mode configurable via CLO_MCP_SEAM_MODE env var
  - Real length checking from stored edge_geometry in state
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

from semantic.geometry import get_edge_length, Edge
from semantic.state_manager import StateManager


# Default 5% tolerance for edge length matching
_DEFAULT_TOLERANCE = 0.05


def _get_seam_tolerance() -> float:
    raw = os.environ.get("CLO_MCP_SEAM_TOLERANCE", "")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return _DEFAULT_TOLERANCE


def _get_seam_mode() -> str:
    """Get seam validation mode: 'warn' (default) or 'strict'."""
    mode = os.environ.get("CLO_MCP_SEAM_MODE", "warn").strip().lower()
    if mode in ("warn", "strict"):
        return mode
    return "warn"


@dataclass
class SeamPlanResult:
    """Result of planning a single seam."""
    success: bool
    seam_name: str | None = None
    error: str | None = None
    hint: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class FullSeamPlanResult:
    """Result of executing a complete seam plan."""
    success: bool
    seams_created: list[str] = field(default_factory=list)
    seams_failed: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    hint: str | None = None


class SeamPlanner:
    """
    Plans and executes seams using semantic edge labels.

    Args:
        state: The garment StateManager instance.
        bridge_fn: Callable that sends commands to the CLO bridge.
    """

    def __init__(
        self,
        state: StateManager,
        bridge_fn: Callable[[str, dict | None], dict],
    ):
        self.state = state
        self.bridge_fn = bridge_fn
        self.tolerance = _get_seam_tolerance()
        self.mode = _get_seam_mode()

    def plan_seam(
        self,
        pattern_a_name: str,
        edge_a: str,
        pattern_b_name: str,
        edge_b: str,
        flip: bool = False,
        label: str = "",
    ) -> SeamPlanResult:
        """
        Plan and execute a single seam between two named pattern edges.

        Args:
            pattern_a_name: Name of first pattern piece.
            edge_a: Semantic edge label on pattern A (e.g. "left", "top").
            pattern_b_name: Name of second pattern piece.
            edge_b: Semantic edge label on pattern B.
            flip: If True, reverse directionB (for opposing seam alignment).
            label: Optional human-readable label for this seam.
        """
        warnings: list[str] = []

        # --- Validate pattern A ---
        entry_a = self.state.get_pattern_by_name(pattern_a_name)
        if not entry_a:
            return SeamPlanResult(
                success=False,
                error=f"Pattern '{pattern_a_name}' not found in state.",
                hint="Use create_piece to create this pattern first, or load_state to re-sync.",
            )

        # --- Validate pattern B ---
        entry_b = self.state.get_pattern_by_name(pattern_b_name)
        if not entry_b:
            return SeamPlanResult(
                success=False,
                error=f"Pattern '{pattern_b_name}' not found in state.",
                hint="Use create_piece to create this pattern first, or load_state to re-sync.",
            )

        # --- Validate edge A ---
        line_a = entry_a.get("edges", {}).get(edge_a)
        if line_a is None:
            available = list(entry_a.get("edges", {}).keys())
            return SeamPlanResult(
                success=False,
                error=f"Edge '{edge_a}' not found on pattern '{pattern_a_name}'.",
                hint=f"Available edges: {available}. Check get_garment_state for edge labels.",
            )

        # --- Validate edge B ---
        line_b = entry_b.get("edges", {}).get(edge_b)
        if line_b is None:
            available = list(entry_b.get("edges", {}).keys())
            return SeamPlanResult(
                success=False,
                error=f"Edge '{edge_b}' not found on pattern '{pattern_b_name}'.",
                hint=f"Available edges: {available}. Check get_garment_state for edge labels.",
            )

        # --- Edge length check ---
        length_error = self._check_edge_lengths(
            entry_a, edge_a, entry_b, edge_b, warnings
        )
        if length_error:
            return length_error

        # --- Execute seam via bridge ---
        pattern_a_idx = entry_a["index"]
        pattern_b_idx = entry_b["index"]
        direction_a = True
        direction_b = not flip  # flip reverses direction B

        result = self.bridge_fn("add_seam", {
            "pattern_a": pattern_a_idx,
            "line_a": line_a,
            "pattern_b": pattern_b_idx,
            "line_b": line_b,
            "direction_a": direction_a,
            "direction_b": direction_b,
        })

        if "error" in result:
            return SeamPlanResult(
                success=False,
                error=f"Bridge error: {result['error']}",
                hint="Check CLO is running and edges are valid.",
                warnings=warnings,
            )

        seam_name = label or result.get("seam_name", "unnamed_seam")

        # --- Record in state ---
        self.state.register_seam(
            group_name=seam_name,
            pattern_a_name=pattern_a_name,
            edge_a=edge_a,
            pattern_b_name=pattern_b_name,
            edge_b=edge_b,
        )

        return SeamPlanResult(
            success=True,
            seam_name=seam_name,
            warnings=warnings,
        )

    def execute_seam_plan(
        self, seam_definitions: list[dict]
    ) -> FullSeamPlanResult:
        """
        Execute a full seam plan (list of SeamDefinition-like dicts).

        Each dict must have:
          pattern_a, edge_a, pattern_b, edge_b, label
        Optional: flip (default False)

        Validates ALL pieces exist before attempting any seams.
        """
        # --- Pre-validate all patterns exist ---
        missing_patterns: set[str] = set()
        for sd in seam_definitions:
            for key in ("pattern_a", "pattern_b"):
                name = sd.get(key, "")
                if not self.state.get_pattern_by_name(name):
                    missing_patterns.add(name)

        if missing_patterns:
            return FullSeamPlanResult(
                success=False,
                error=f"Missing patterns: {sorted(missing_patterns)}",
                hint="Create all pattern pieces before executing seam plan.",
            )

        # --- Execute seams ---
        all_warnings: list[str] = []
        created: list[str] = []
        failed: list[dict] = []

        for sd in seam_definitions:
            result = self.plan_seam(
                pattern_a_name=sd["pattern_a"],
                edge_a=sd["edge_a"],
                pattern_b_name=sd["pattern_b"],
                edge_b=sd["edge_b"],
                flip=sd.get("flip", False),
                label=sd.get("label", ""),
            )
            all_warnings.extend(result.warnings)
            if result.success:
                created.append(result.seam_name or "")
            else:
                failed.append({
                    "label": sd.get("label", ""),
                    "error": result.error,
                    "hint": result.hint,
                })

        success = len(failed) == 0
        return FullSeamPlanResult(
            success=success,
            seams_created=created,
            seams_failed=failed,
            warnings=all_warnings,
        )

    def _check_edge_lengths(
        self,
        entry_a: dict,
        edge_a: str,
        entry_b: dict,
        edge_b: str,
        warnings: list[str],
    ) -> SeamPlanResult | None:
        """
        Check that two edges are within tolerance of each other's length.

        In 'warn' mode: appends a warning if they differ, returns None.
        In 'strict' mode: returns a failure SeamPlanResult if mismatch
        exceeds tolerance.

        Uses stored edge_geometry from state (V3) for real length data.
        Falls back to creation_points snapshot if edge_geometry unavailable.
        """
        len_a = self._get_edge_length_from_state(entry_a, edge_a)
        len_b = self._get_edge_length_from_state(entry_b, edge_b)

        if len_a is None or len_b is None:
            return None  # Can't check without geometry data

        if len_a == 0 or len_b == 0:
            msg = (
                f"Zero-length edge detected: "
                f"{entry_a['name']}.{edge_a}={len_a}mm, "
                f"{entry_b['name']}.{edge_b}={len_b}mm"
            )
            warnings.append(msg)
            if self.mode == "strict":
                return SeamPlanResult(
                    success=False,
                    error=msg,
                    hint="Zero-length edges cannot be sewn in strict mode.",
                    warnings=warnings,
                )
            return None

        ratio = abs(len_a - len_b) / max(len_a, len_b)
        if ratio > self.tolerance:
            msg = (
                f"Edge length mismatch ({ratio:.1%} > {self.tolerance:.0%} tolerance): "
                f"{entry_a['name']}.{edge_a}={len_a:.1f}mm vs "
                f"{entry_b['name']}.{edge_b}={len_b:.1f}mm. "
                f"These may be the wrong edges to sew."
            )
            if self.mode == "strict":
                return SeamPlanResult(
                    success=False,
                    error=msg,
                    hint="Seam blocked by strict mode. Adjust edges or set CLO_MCP_SEAM_MODE=warn.",
                    warnings=warnings,
                )
            warnings.append(msg)

        return None

    def _get_edge_length_from_state(
        self, entry: dict, edge_label: str
    ) -> float | None:
        """
        Get the arc length for an edge from stored state data.

        Tries edge_geometry first (V3), then falls back to rebuilding
        from creation_points snapshot.
        """
        # V3: check edge_geometry stored in state
        edge_geom = entry.get("edge_geometry", {})
        geom_entry = edge_geom.get(edge_label)
        if geom_entry and "arc_length" in geom_entry:
            return geom_entry["arc_length"]

        # Fallback: rebuild from creation_points snapshot
        snapshot = entry.get("pattern_json_snapshot", {})
        creation_pts = snapshot.get("creation_points")
        if creation_pts:
            from semantic.geometry import (
                parse_points,
                build_edges_from_creation_points,
                classify_edges_extended,
                get_edge_length,
            )
            parsed = parse_points(creation_pts)
            edges = build_edges_from_creation_points(parsed)
            classification = classify_edges_extended(edges)
            return get_edge_length(edges, edge_label, classification.labels)

        return None

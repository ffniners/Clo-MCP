"""
Seam Planner — translates semantic seam descriptions into CLO API calls.

Maps (patternA_name, edgeA_label, patternB_name, edgeB_label) into
AddSeamlinePairGroup(patternA_index, lineA_index, patternB_index, lineB_index,
                     directionA, directionB).

Validates:
  - Both patterns exist in state
  - Both edges exist in state
  - Edge lengths are within tolerance (configurable via CLO_MCP_SEAM_TOLERANCE)

The tolerance check warns but does not block — the caller may have valid
reasons for sewing edges of different lengths.
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
        self._check_edge_lengths(entry_a, edge_a, entry_b, edge_b, warnings)

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
    ) -> None:
        """
        Check that two edges are within tolerance of each other's length.
        Appends a warning if they differ.

        This reads from the pattern_json_snapshot in state if available,
        otherwise skips the check.
        """
        # We can estimate length from the edges dict if we have the
        # creation points stored. For now, we rely on the snapshot
        # containing point data that we can use to compute length.
        # If snapshots aren't available, we skip with a note.

        snapshot_a = entry_a.get("pattern_json_snapshot", {})
        snapshot_b = entry_b.get("pattern_json_snapshot", {})

        if not snapshot_a or not snapshot_b:
            return  # Can't check without snapshots

        # Try to compute from stored edge data
        edges_a = entry_a.get("_edge_objects")
        edges_b = entry_b.get("_edge_objects")

        if not edges_a or not edges_b:
            return

        labels_a = entry_a.get("edges", {})
        labels_b = entry_b.get("edges", {})

        len_a = get_edge_length(edges_a, edge_a, labels_a)
        len_b = get_edge_length(edges_b, edge_b, labels_b)

        if len_a is None or len_b is None:
            return

        if len_a == 0 or len_b == 0:
            warnings.append(
                f"Zero-length edge detected: "
                f"{entry_a['name']}.{edge_a}={len_a}mm, "
                f"{entry_b['name']}.{edge_b}={len_b}mm"
            )
            return

        ratio = abs(len_a - len_b) / max(len_a, len_b)
        if ratio > self.tolerance:
            warnings.append(
                f"Edge length mismatch ({ratio:.1%} > {self.tolerance:.0%} tolerance): "
                f"{entry_a['name']}.{edge_a}={len_a:.1f}mm vs "
                f"{entry_b['name']}.{edge_b}={len_b:.1f}mm. "
                f"These may be the wrong edges to sew."
            )

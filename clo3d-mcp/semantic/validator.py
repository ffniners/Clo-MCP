"""
Garment Validator — pre-flight checks for garment integrity.

Runs a configurable set of validation checks against garment state
and returns structured results with errors, warnings, and passed checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from semantic.state_manager import StateManager
from semantic.garment_types import get_garment_type, GarmentType


@dataclass
class ValidationCheck:
    """Result of a single validation check."""
    name: str
    passed: bool
    message: str = ""


@dataclass
class ValidationResult:
    """Full validation result."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks_passed: list[str] = field(default_factory=list)


# Default tolerance for edge length comparison (matches seam_planner)
_LENGTH_TOLERANCE = 0.05


class GarmentValidator:
    """Validates garment state for completeness and consistency."""

    def __init__(self, state: StateManager, bridge_fn=None):
        self.state = state
        self.bridge_fn = bridge_fn

    def validate(self, garment_type: str = "") -> ValidationResult:
        """Run all validation checks and return a structured result."""
        checks: list[ValidationCheck] = []

        state_data = self.state.get_state()
        gt = get_garment_type(garment_type) if garment_type else None

        # Check 1: Pattern count
        checks.append(self._check_pattern_count(state_data, gt))

        # Check 2: Required pieces (only if garment type given)
        if gt:
            checks.append(self._check_required_pieces(state_data, gt))

        # Check 3: Seam completeness (only if garment type given)
        if gt:
            checks.append(self._check_seam_completeness(state_data, gt))

        # Check 4: No duplicate seams
        checks.append(self._check_duplicate_seams(state_data))

        # Check 5: Edge length mismatches (warning)
        checks.append(self._check_seam_edge_lengths(state_data))

        # Check 6: Fabric assignment (warning)
        checks.append(self._check_fabric_assignment(state_data))

        # Check 7: Orphan pieces (warning)
        checks.append(self._check_orphan_pieces(state_data))

        # Compile results
        errors = []
        warnings = []
        checks_passed = []

        for check in checks:
            if check.passed:
                checks_passed.append(check.name)
            elif check.name.startswith("warn_"):
                warnings.append(check.message)
            else:
                errors.append(check.message)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            checks_passed=checks_passed,
        )

    # -----------------------------------------------------------------
    # Individual checks
    # -----------------------------------------------------------------

    def _check_pattern_count(
        self, state_data: dict, gt: GarmentType | None
    ) -> ValidationCheck:
        """Check if pattern count matches garment type expectation."""
        pattern_count = len(state_data.get("patterns", {}))
        if pattern_count == 0:
            return ValidationCheck(
                name="pattern_count", passed=False,
                message="No patterns registered in state.",
            )
        if gt:
            expected = len(gt.pieces)
            if pattern_count != expected:
                return ValidationCheck(
                    name="pattern_count", passed=False,
                    message=(
                        f"Expected {expected} patterns for {gt.name}, "
                        f"found {pattern_count}."
                    ),
                )
        return ValidationCheck(name="pattern_count", passed=True)

    def _check_required_pieces(
        self, state_data: dict, gt: GarmentType
    ) -> ValidationCheck:
        """Check that all required pieces (by role) exist."""
        existing_roles = {
            e.get("role", "") for e in state_data.get("patterns", {}).values()
        }
        expected_roles = {p.role for p in gt.pieces}
        missing = expected_roles - existing_roles
        if missing:
            return ValidationCheck(
                name="required_pieces", passed=False,
                message=(
                    f"Missing required pieces for {gt.name}: {sorted(missing)}"
                ),
            )
        return ValidationCheck(name="required_pieces", passed=True)

    def _check_seam_completeness(
        self, state_data: dict, gt: GarmentType
    ) -> ValidationCheck:
        """Check that all expected seams exist."""
        expected_labels = {sd.label for sd in gt.seam_plan if sd.label}
        existing_labels = {
            s.get("group_name", "") for s in state_data.get("seams", [])
        }
        missing = expected_labels - existing_labels
        if missing:
            return ValidationCheck(
                name="seam_completeness", passed=False,
                message=(
                    f"Missing seams for {gt.name}: {sorted(missing)}"
                ),
            )
        return ValidationCheck(name="seam_completeness", passed=True)

    def _check_duplicate_seams(self, state_data: dict) -> ValidationCheck:
        """Check for duplicate seams (same edge pair sewn twice)."""
        seen: set[tuple] = set()
        duplicates: list[str] = []
        for seam in state_data.get("seams", []):
            key = (
                seam.get("patternA"), seam.get("edgeA"),
                seam.get("patternB"), seam.get("edgeB"),
            )
            if key in seen:
                duplicates.append(seam.get("group_name", "unnamed"))
            seen.add(key)
        if duplicates:
            return ValidationCheck(
                name="duplicate_seams", passed=False,
                message=f"Duplicate seams found: {duplicates}",
            )
        return ValidationCheck(name="duplicate_seams", passed=True)

    def _check_seam_edge_lengths(self, state_data: dict) -> ValidationCheck:
        """Check that sewn edge pairs have compatible lengths."""
        mismatches: list[str] = []
        for seam in state_data.get("seams", []):
            pattern_a = self._find_pattern_by_name(
                state_data, seam.get("patternA", "")
            )
            pattern_b = self._find_pattern_by_name(
                state_data, seam.get("patternB", "")
            )
            if not pattern_a or not pattern_b:
                continue
            geom_a = pattern_a.get("edge_geometry", {}).get(
                seam.get("edgeA", ""), {}
            )
            geom_b = pattern_b.get("edge_geometry", {}).get(
                seam.get("edgeB", ""), {}
            )
            len_a = geom_a.get("arc_length")
            len_b = geom_b.get("arc_length")
            if len_a and len_b and max(len_a, len_b) > 0:
                ratio = abs(len_a - len_b) / max(len_a, len_b)
                if ratio > _LENGTH_TOLERANCE:
                    mismatches.append(
                        f"{seam.get('group_name')}: "
                        f"{len_a:.1f}mm vs {len_b:.1f}mm ({ratio:.0%})"
                    )
        if mismatches:
            return ValidationCheck(
                name="warn_edge_length_mismatch", passed=False,
                message=f"Edge length mismatches in seams: {mismatches}",
            )
        return ValidationCheck(name="warn_edge_length_mismatch", passed=True)

    def _check_fabric_assignment(self, state_data: dict) -> ValidationCheck:
        """Check that all patterns have a fabric assigned."""
        unassigned: list[str] = []
        for entry in state_data.get("patterns", {}).values():
            if entry.get("fabric_index") is None:
                unassigned.append(entry.get("name", "unnamed"))
        if unassigned:
            return ValidationCheck(
                name="warn_fabric_assignment", passed=False,
                message=f"Patterns without fabric: {sorted(unassigned)}",
            )
        return ValidationCheck(name="warn_fabric_assignment", passed=True)

    def _check_orphan_pieces(self, state_data: dict) -> ValidationCheck:
        """Check for pieces not referenced by any seam."""
        all_pattern_names = {
            e.get("name", "")
            for e in state_data.get("patterns", {}).values()
        }
        patterns_in_seams: set[str] = set()
        for seam in state_data.get("seams", []):
            patterns_in_seams.add(seam.get("patternA", ""))
            patterns_in_seams.add(seam.get("patternB", ""))

        orphans = all_pattern_names - patterns_in_seams
        # Only flag orphans if there ARE seams (otherwise everything is an orphan)
        if orphans and state_data.get("seams"):
            return ValidationCheck(
                name="warn_orphan_pieces", passed=False,
                message=f"Orphan pieces (not in any seam): {sorted(orphans)}",
            )
        return ValidationCheck(name="warn_orphan_pieces", passed=True)

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _find_pattern_by_name(state_data: dict, name: str) -> dict | None:
        for entry in state_data.get("patterns", {}).values():
            if entry.get("name") == name:
                return entry
        return None

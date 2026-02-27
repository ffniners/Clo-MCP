"""
State Manager — persistent garment state between sessions.

Maintains garment_state.json on disk. Written after every mutation.
On startup, loads from disk and re-syncs with CLO (pattern names → indices).

State file path is configurable via CLO_MCP_STATE_PATH env var,
defaulting to ./state/garment_state.json.

V3 additions:
  - Atomic writes (temp file + os.replace)
  - Revision counter for concurrency safety
  - State version 3 with migration from V2
  - Normalized edge geometry storage for downstream seam checks
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable


_DEFAULT_STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "state", "garment_state.json"
)

STATE_VERSION = 3
PREVIOUS_STATE_VERSION = 2


def _get_state_path() -> str:
    return os.environ.get("CLO_MCP_STATE_PATH", _DEFAULT_STATE_PATH)


def _empty_state() -> dict:
    return {
        "version": STATE_VERSION,
        "revision": 0,
        "updated_at": None,
        "patterns": {},
        "fabrics": {},
        "seams": [],
        "colorways": [],
    }


def _migrate_v2_to_v3(data: dict) -> dict:
    """Migrate a V2 state dict to V3 format."""
    data["version"] = STATE_VERSION
    if "revision" not in data:
        data["revision"] = 0
    if "updated_at" not in data:
        data["updated_at"] = None
    # V2 patterns didn't store edge_geometry; leave empty for re-derivation
    for key, entry in data.get("patterns", {}).items():
        if "edge_geometry" not in entry:
            entry["edge_geometry"] = {}
    return data


class StateManager:
    """
    Manages garment state: patterns, fabrics, seams, colorways.

    The bridge_fn parameter is a callable that sends commands to the
    CLO bridge and returns the parsed response dict.  This decouples
    the state manager from socket details.
    """

    def __init__(self, bridge_fn: Callable[[str, dict | None], dict] | None = None):
        self.bridge_fn = bridge_fn
        self._state: dict = _empty_state()
        self._state_path = _get_state_path()
        self._load()

    # -----------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------

    def _load(self) -> None:
        """Load state from disk, or create fresh if missing/corrupt."""
        path = self._state_path
        if os.path.isfile(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                version = data.get("version")
                if version == STATE_VERSION:
                    self._state = data
                elif version == PREVIOUS_STATE_VERSION:
                    self._state = _migrate_v2_to_v3(data)
                    self._save()  # persist migration
                else:
                    # Unknown version — start fresh
                    self._state = _empty_state()
            except (json.JSONDecodeError, KeyError):
                self._state = _empty_state()
        else:
            self._state = _empty_state()

    def _save(self) -> None:
        """Persist current state to disk atomically (temp file + replace)."""
        path = self._state_path
        dir_path = os.path.dirname(path)
        os.makedirs(dir_path, exist_ok=True)

        self._state["revision"] = self._state.get("revision", 0) + 1
        self._state["updated_at"] = time.time()

        # Atomic write: write to temp file in same directory, then replace
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._state, f, indent=2)
            os.replace(tmp_path, path)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def clear(self) -> None:
        """Wipe state to empty. Does NOT modify CLO scene."""
        self._state = _empty_state()
        self._save()

    # -----------------------------------------------------------------
    # Read accessors
    # -----------------------------------------------------------------

    def get_state(self) -> dict:
        """Return a deep copy of current state."""
        return deepcopy(self._state)

    def get_revision(self) -> int:
        """Return the current state revision number."""
        return self._state.get("revision", 0)

    def get_pattern_by_name(self, name: str) -> dict | None:
        """Look up a pattern entry by name."""
        for entry in self._state["patterns"].values():
            if entry.get("name") == name:
                return deepcopy(entry)
        return None

    def get_pattern_by_role(self, role: str) -> dict | None:
        """Look up a pattern entry by its garment role."""
        for entry in self._state["patterns"].values():
            if entry.get("role") == role:
                return deepcopy(entry)
        return None

    def get_pattern_index(self, name: str) -> int | None:
        """Get CLO pattern index by name. Returns None if not in state."""
        entry = self.get_pattern_by_name(name)
        return entry["index"] if entry else None

    def get_fabric_by_name(self, name: str) -> dict | None:
        """Look up a fabric entry by friendly name."""
        for entry in self._state["fabrics"].values():
            if entry.get("name") == name:
                return deepcopy(entry)
        return None

    def get_edge_index(self, pattern_name: str, edge_label: str) -> int | None:
        """Get line index for a named edge on a named pattern."""
        entry = self.get_pattern_by_name(pattern_name)
        if not entry:
            return None
        edges = entry.get("edges", {})
        return edges.get(edge_label)

    def get_edge_geometry(self, pattern_name: str) -> dict:
        """Get stored edge geometry for a pattern (lengths, curvatures)."""
        entry = self.get_pattern_by_name(pattern_name)
        if not entry:
            return {}
        return entry.get("edge_geometry", {})

    # -----------------------------------------------------------------
    # Mutations
    # -----------------------------------------------------------------

    def register_pattern(
        self,
        index: int,
        name: str,
        role: str = "",
        edges: dict[str, int] | None = None,
        pattern_json_snapshot: dict | None = None,
        edge_geometry: dict | None = None,
    ) -> None:
        """Register or update a pattern piece in state."""
        key = str(index)
        self._state["patterns"][key] = {
            "index": index,
            "name": name,
            "role": role,
            "edges": edges or {},
            "fabric_index": None,
            "pattern_json_snapshot": pattern_json_snapshot or {},
            "edge_geometry": edge_geometry or {},
        }
        self._save()

    def update_edges(self, pattern_index: int, edges: dict[str, int],
                     edge_geometry: dict | None = None) -> None:
        """Update the edge label → line_index mapping for a pattern."""
        key = str(pattern_index)
        if key in self._state["patterns"]:
            self._state["patterns"][key]["edges"] = edges
            if edge_geometry is not None:
                self._state["patterns"][key]["edge_geometry"] = edge_geometry
            self._save()

    def update_pattern_json_snapshot(
        self, pattern_index: int, snapshot: dict
    ) -> None:
        """Store the raw PatternJSON for a pattern (for debugging)."""
        key = str(pattern_index)
        if key in self._state["patterns"]:
            self._state["patterns"][key]["pattern_json_snapshot"] = snapshot
            self._save()

    def register_fabric(
        self, index: int, name: str, path: str = ""
    ) -> None:
        """Register or update a fabric in state."""
        key = str(index)
        self._state["fabrics"][key] = {
            "index": index,
            "name": name,
            "path": path,
        }
        self._save()

    def assign_fabric_to_pattern(
        self, fabric_index: int, pattern_index: int
    ) -> None:
        """Record that a fabric is assigned to a pattern."""
        key = str(pattern_index)
        if key in self._state["patterns"]:
            self._state["patterns"][key]["fabric_index"] = fabric_index
            self._save()

    def register_seam(
        self,
        group_name: str,
        pattern_a_name: str,
        edge_a: str,
        pattern_b_name: str,
        edge_b: str,
    ) -> None:
        """Record a seam in state."""
        self._state["seams"].append({
            "group_name": group_name,
            "patternA": pattern_a_name,
            "edgeA": edge_a,
            "patternB": pattern_b_name,
            "edgeB": edge_b,
        })
        self._save()

    # -----------------------------------------------------------------
    # Re-sync with CLO
    # -----------------------------------------------------------------

    def sync_with_clo(self) -> list[str]:
        """
        Re-sync state with CLO after a CLO restart.
        Queries CLO for current pattern names/indices and updates state.
        Returns a list of warnings for patterns that no longer exist.
        """
        if not self.bridge_fn:
            return ["No bridge function configured — cannot sync with CLO"]

        warnings = []
        result = self.bridge_fn("get_pattern_count", None)
        if "error" in result:
            return [f"Bridge error during sync: {result['error']}"]

        clo_count = result.get("pattern_count", 0)

        # Build name→index map from CLO
        clo_patterns: dict[str, int] = {}
        for i in range(clo_count):
            name_result = self.bridge_fn("get_pattern_name", {"pattern_index": i})
            if "error" not in name_result:
                clo_patterns[name_result.get("name", "")] = i

        # Update state entries
        updated: dict[str, dict] = {}
        for key, entry in self._state["patterns"].items():
            name = entry.get("name", "")
            if name in clo_patterns:
                entry["index"] = clo_patterns[name]
                updated[str(clo_patterns[name])] = entry
            else:
                warnings.append(
                    f"Pattern '{name}' (role={entry.get('role')}) "
                    f"no longer exists in CLO scene — keeping in state "
                    f"but index may be stale."
                )
                updated[key] = entry

        self._state["patterns"] = updated
        self._save()
        return warnings

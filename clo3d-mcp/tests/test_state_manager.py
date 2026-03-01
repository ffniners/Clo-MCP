"""
Tests for state_manager.py — persistence, migration, atomic writes, versioning.
"""

import json
import os
import tempfile

import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from semantic.state_manager import (
    StateManager,
    STATE_VERSION,
    PREVIOUS_STATE_VERSION,
    _empty_state,
    _migrate_v2_to_v3,
    _migrate_v3_to_v4,
)


@pytest.fixture
def tmp_state_path(tmp_path):
    """Create a temporary state file path and set the env var."""
    path = str(tmp_path / "test_state.json")
    os.environ["CLO_MCP_STATE_PATH"] = path
    yield path
    os.environ.pop("CLO_MCP_STATE_PATH", None)


@pytest.fixture
def state_manager(tmp_state_path):
    """Create a fresh StateManager with no bridge."""
    return StateManager(bridge_fn=None)


class TestEmptyState:
    def test_version(self):
        s = _empty_state()
        assert s["version"] == STATE_VERSION

    def test_revision_starts_at_zero(self):
        s = _empty_state()
        assert s["revision"] == 0

    def test_has_all_keys(self):
        s = _empty_state()
        for key in ("version", "revision", "updated_at", "patterns", "fabrics",
                     "seams", "colorways", "measurements"):
            assert key in s


class TestStateManagerPersistence:
    def test_fresh_state(self, state_manager, tmp_state_path):
        """Fresh StateManager creates empty state."""
        state = state_manager.get_state()
        assert state["version"] == STATE_VERSION
        assert state["patterns"] == {}
        assert state["fabrics"] == {}
        assert state["seams"] == []

    def test_register_pattern_persists(self, state_manager, tmp_state_path):
        """Registered pattern is persisted to disk."""
        state_manager.register_pattern(
            index=0, name="Front", role="front_bodice",
            edges={"top": 1, "bottom": 3},
            edge_geometry={"top": {"arc_length": 300.0}},
        )
        # Read from disk directly
        with open(tmp_state_path) as f:
            data = json.load(f)
        assert "0" in data["patterns"]
        assert data["patterns"]["0"]["name"] == "Front"
        assert data["patterns"]["0"]["edge_geometry"]["top"]["arc_length"] == 300.0

    def test_revision_increments(self, state_manager):
        """Each save increments the revision counter."""
        r0 = state_manager.get_revision()
        state_manager.register_pattern(index=0, name="A")
        r1 = state_manager.get_revision()
        state_manager.register_pattern(index=1, name="B")
        r2 = state_manager.get_revision()
        assert r1 > r0
        assert r2 > r1

    def test_updated_at_set(self, state_manager):
        """updated_at is set on save."""
        state_manager.register_pattern(index=0, name="A")
        state = state_manager.get_state()
        assert state["updated_at"] is not None
        assert isinstance(state["updated_at"], float)

    def test_clear_resets(self, state_manager):
        """Clear resets state to empty."""
        state_manager.register_pattern(index=0, name="A")
        state_manager.clear()
        assert state_manager.get_state()["patterns"] == {}

    def test_reload_preserves_data(self, tmp_state_path):
        """Creating a new StateManager loads persisted data."""
        sm1 = StateManager(bridge_fn=None)
        sm1.register_pattern(index=0, name="Test", role="test")
        # Create new StateManager — should load from disk
        sm2 = StateManager(bridge_fn=None)
        entry = sm2.get_pattern_by_name("Test")
        assert entry is not None
        assert entry["role"] == "test"


class TestAtomicWrites:
    def test_state_file_valid_json(self, state_manager, tmp_state_path):
        """State file is always valid JSON after writes."""
        state_manager.register_pattern(index=0, name="A")
        state_manager.register_fabric(index=0, name="Fabric", path="/test.zfab")
        state_manager.register_seam("seam1", "A", "top", "B", "bottom")

        with open(tmp_state_path) as f:
            data = json.load(f)
        assert data["version"] == STATE_VERSION

    def test_no_temp_files_left(self, state_manager, tmp_state_path):
        """No .tmp files are left after successful writes."""
        state_manager.register_pattern(index=0, name="A")
        dir_path = os.path.dirname(tmp_state_path)
        tmp_files = [f for f in os.listdir(dir_path) if f.endswith(".tmp")]
        assert len(tmp_files) == 0


class TestV2Migration:
    def test_migrate_v2_to_v3(self):
        """V2 state dict is migrated to V3 format."""
        v2_data = {
            "version": 2,
            "patterns": {
                "0": {
                    "index": 0, "name": "Front", "role": "front",
                    "edges": {"top": 1}, "fabric_index": None,
                    "pattern_json_snapshot": {},
                }
            },
            "fabrics": {},
            "seams": [],
            "colorways": [],
        }
        v3_data = _migrate_v2_to_v3(v2_data)
        assert v3_data["version"] == 3
        assert v3_data["revision"] == 0
        assert "updated_at" in v3_data
        assert v3_data["patterns"]["0"]["edge_geometry"] == {}

    def test_load_v2_file(self, tmp_state_path):
        """StateManager loads and migrates a V2 state file through V3 to V4."""
        v2_state = {
            "version": 2,
            "patterns": {
                "0": {
                    "index": 0, "name": "Old_Pattern", "role": "test",
                    "edges": {"left": 0}, "fabric_index": None,
                    "pattern_json_snapshot": {},
                }
            },
            "fabrics": {},
            "seams": [],
            "colorways": [],
        }
        os.makedirs(os.path.dirname(tmp_state_path), exist_ok=True)
        with open(tmp_state_path, "w") as f:
            json.dump(v2_state, f)

        sm = StateManager(bridge_fn=None)
        state = sm.get_state()
        assert state["version"] == STATE_VERSION
        assert "measurements" in state
        entry = sm.get_pattern_by_name("Old_Pattern")
        assert entry is not None
        assert entry["edge_geometry"] == {}

    def test_unknown_version_starts_fresh(self, tmp_state_path):
        """Unknown state version triggers fresh start."""
        old_state = {"version": 999, "patterns": {"0": {"name": "X"}}}
        os.makedirs(os.path.dirname(tmp_state_path), exist_ok=True)
        with open(tmp_state_path, "w") as f:
            json.dump(old_state, f)

        sm = StateManager(bridge_fn=None)
        assert sm.get_state()["patterns"] == {}


class TestV3Migration:
    def test_migrate_v3_to_v4(self):
        """V3 state dict is migrated to V4 format."""
        v3_data = {
            "version": 3,
            "revision": 5,
            "updated_at": 1234567890.0,
            "patterns": {},
            "fabrics": {},
            "seams": [],
            "colorways": [],
        }
        v4_data = _migrate_v3_to_v4(v3_data)
        assert v4_data["version"] == STATE_VERSION
        assert v4_data["measurements"] == {}
        assert v4_data["revision"] == 5  # preserved

    def test_load_v3_file(self, tmp_state_path):
        """StateManager loads and migrates a V3 state file to V4."""
        v3_state = {
            "version": 3,
            "revision": 3,
            "updated_at": 1000.0,
            "patterns": {
                "0": {
                    "index": 0, "name": "Test", "role": "test",
                    "edges": {"top": 1}, "fabric_index": None,
                    "pattern_json_snapshot": {},
                    "edge_geometry": {"top": {"arc_length": 100.0}},
                }
            },
            "fabrics": {},
            "seams": [],
            "colorways": [],
        }
        os.makedirs(os.path.dirname(tmp_state_path), exist_ok=True)
        with open(tmp_state_path, "w") as f:
            json.dump(v3_state, f)

        sm = StateManager(bridge_fn=None)
        state = sm.get_state()
        assert state["version"] == STATE_VERSION
        assert "measurements" in state
        assert state["measurements"] == {}
        entry = sm.get_pattern_by_name("Test")
        assert entry is not None

    def test_v2_chain_migration(self, tmp_state_path):
        """V2 file migrates through V3 to V4."""
        v2_state = {
            "version": 2,
            "patterns": {
                "0": {
                    "index": 0, "name": "Chain", "role": "chain_test",
                    "edges": {}, "fabric_index": None,
                    "pattern_json_snapshot": {},
                }
            },
            "fabrics": {},
            "seams": [],
            "colorways": [],
        }
        os.makedirs(os.path.dirname(tmp_state_path), exist_ok=True)
        with open(tmp_state_path, "w") as f:
            json.dump(v2_state, f)

        sm = StateManager(bridge_fn=None)
        state = sm.get_state()
        assert state["version"] == STATE_VERSION
        assert "measurements" in state
        assert "revision" in state
        assert state["patterns"]["0"]["edge_geometry"] == {}


class TestStateManagerAccessors:
    def test_get_pattern_by_name(self, state_manager):
        state_manager.register_pattern(index=0, name="Front", role="front_bodice")
        entry = state_manager.get_pattern_by_name("Front")
        assert entry is not None
        assert entry["role"] == "front_bodice"

    def test_get_pattern_by_name_missing(self, state_manager):
        assert state_manager.get_pattern_by_name("nonexistent") is None

    def test_get_pattern_by_role(self, state_manager):
        state_manager.register_pattern(index=0, name="Front", role="front_bodice")
        entry = state_manager.get_pattern_by_role("front_bodice")
        assert entry is not None
        assert entry["name"] == "Front"

    def test_get_pattern_index(self, state_manager):
        state_manager.register_pattern(index=5, name="Test")
        assert state_manager.get_pattern_index("Test") == 5
        assert state_manager.get_pattern_index("missing") is None

    def test_get_fabric_by_name(self, state_manager):
        state_manager.register_fabric(index=0, name="Cotton", path="/cotton.zfab")
        fabric = state_manager.get_fabric_by_name("Cotton")
        assert fabric is not None
        assert fabric["path"] == "/cotton.zfab"

    def test_get_edge_index(self, state_manager):
        state_manager.register_pattern(
            index=0, name="Front", edges={"top": 1, "bottom": 3}
        )
        assert state_manager.get_edge_index("Front", "top") == 1
        assert state_manager.get_edge_index("Front", "missing") is None

    def test_get_edge_geometry(self, state_manager):
        state_manager.register_pattern(
            index=0, name="Front",
            edge_geometry={"top": {"arc_length": 300.0}}
        )
        geom = state_manager.get_edge_geometry("Front")
        assert geom["top"]["arc_length"] == 300.0

    def test_deep_copy_isolation(self, state_manager):
        """Returned state dicts are deep copies (mutations don't affect internal state)."""
        state_manager.register_pattern(index=0, name="Front", edges={"top": 1})
        entry = state_manager.get_pattern_by_name("Front")
        entry["edges"]["injected"] = 99
        # Internal state should not be affected
        entry2 = state_manager.get_pattern_by_name("Front")
        assert "injected" not in entry2["edges"]


class TestStateManagerMutations:
    def test_update_edges(self, state_manager):
        state_manager.register_pattern(index=0, name="Front", edges={"top": 1})
        state_manager.update_edges(0, {"top": 2, "left": 0},
                                   edge_geometry={"top": {"arc_length": 500.0}})
        entry = state_manager.get_pattern_by_name("Front")
        assert entry["edges"]["top"] == 2
        assert entry["edge_geometry"]["top"]["arc_length"] == 500.0

    def test_assign_fabric_to_pattern(self, state_manager):
        state_manager.register_pattern(index=0, name="Front")
        state_manager.register_fabric(index=0, name="Cotton")
        state_manager.assign_fabric_to_pattern(fabric_index=0, pattern_index=0)
        entry = state_manager.get_pattern_by_name("Front")
        assert entry["fabric_index"] == 0

    def test_register_seam(self, state_manager):
        state_manager.register_seam("seam1", "A", "top", "B", "bottom")
        state = state_manager.get_state()
        assert len(state["seams"]) == 1
        assert state["seams"][0]["group_name"] == "seam1"

    def test_update_pattern_json_snapshot(self, state_manager):
        state_manager.register_pattern(index=0, name="Front")
        state_manager.update_pattern_json_snapshot(0, {"test_key": "test_val"})
        entry = state_manager.get_pattern_by_name("Front")
        assert entry["pattern_json_snapshot"]["test_key"] == "test_val"


class TestMeasurements:
    def test_register_measurements(self, state_manager):
        state_manager.register_measurements("t_shirt", {"chest_width_mm": 500})
        m = state_manager.get_measurements()
        assert m["garment_type"] == "t_shirt"
        assert m["values"]["chest_width_mm"] == 500

    def test_get_measurements_empty(self, state_manager):
        m = state_manager.get_measurements()
        assert m == {}

    def test_clear_measurements(self, state_manager):
        state_manager.register_measurements("t_shirt", {"chest_width_mm": 500})
        state_manager.clear_measurements()
        assert state_manager.get_measurements() == {}

    def test_measurements_deep_copy(self, state_manager):
        state_manager.register_measurements("t_shirt", {"chest_width_mm": 500})
        m = state_manager.get_measurements()
        m["values"]["chest_width_mm"] = 999
        m2 = state_manager.get_measurements()
        assert m2["values"]["chest_width_mm"] == 500

    def test_measurements_persisted(self, tmp_state_path):
        sm1 = StateManager(bridge_fn=None)
        sm1.register_measurements("t_shirt", {"body_length_mm": 700})
        sm2 = StateManager(bridge_fn=None)
        m = sm2.get_measurements()
        assert m["garment_type"] == "t_shirt"
        assert m["values"]["body_length_mm"] == 700


class TestDeletePatternByName:
    def test_delete_existing(self, state_manager):
        state_manager.register_pattern(index=0, name="Front", role="front")
        assert state_manager.delete_pattern_by_name("Front") is True
        assert state_manager.get_pattern_by_name("Front") is None

    def test_delete_nonexistent(self, state_manager):
        assert state_manager.delete_pattern_by_name("Ghost") is False

    def test_delete_preserves_others(self, state_manager):
        state_manager.register_pattern(index=0, name="Front", role="front")
        state_manager.register_pattern(index=1, name="Back", role="back")
        state_manager.delete_pattern_by_name("Front")
        assert state_manager.get_pattern_by_name("Back") is not None
        assert len(state_manager.get_state()["patterns"]) == 1


class TestBulkRegisterPatterns:
    def test_bulk_register(self, state_manager):
        patterns = [
            {"index": 0, "name": "A", "role": "front", "edges": {"top": 0}},
            {"index": 1, "name": "B", "role": "back", "edges": {"top": 0}},
            {"index": 2, "name": "C"},
        ]
        state_manager.bulk_register_patterns(patterns)
        state = state_manager.get_state()
        assert len(state["patterns"]) == 3
        assert state["patterns"]["0"]["name"] == "A"
        assert state["patterns"]["1"]["role"] == "back"
        assert state["patterns"]["2"]["role"] == ""

    def test_bulk_register_single_save(self, state_manager):
        r0 = state_manager.get_revision()
        patterns = [
            {"index": 0, "name": "A"},
            {"index": 1, "name": "B"},
        ]
        state_manager.bulk_register_patterns(patterns)
        r1 = state_manager.get_revision()
        assert r1 == r0 + 1  # Only one save


class TestClearSeams:
    def test_clear_seams(self, state_manager):
        state_manager.register_seam("s1", "A", "top", "B", "bottom")
        state_manager.register_seam("s2", "C", "left", "D", "right")
        state_manager.clear_seams()
        assert state_manager.get_state()["seams"] == []

    def test_clear_seams_preserves_patterns(self, state_manager):
        state_manager.register_pattern(index=0, name="Front")
        state_manager.register_seam("s1", "A", "top", "B", "bottom")
        state_manager.clear_seams()
        assert state_manager.get_pattern_by_name("Front") is not None

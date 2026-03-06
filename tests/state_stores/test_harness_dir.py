"""Tests for HarnessDirStateStore."""

from __future__ import annotations

import json
from pathlib import Path

from rigger._types import EpochState
from rigger.state_stores.harness_dir import HarnessDirStateStore


class TestLoad:
    def test_returns_defaults_when_missing(self, tmp_path: Path):
        store = HarnessDirStateStore()
        state = store.load(tmp_path)
        assert state.epoch == 0
        assert state.completed_tasks == []

    def test_loads_existing_state(self, tmp_path: Path):
        harness_dir = tmp_path / ".harness"
        harness_dir.mkdir()
        data = {
            "_schema_version": "1.0",
            "epoch": 5,
            "completed_tasks": ["t1"],
            "pending_tasks": [],
            "halted": False,
            "halt_reason": "",
            "metadata": {},
        }
        (harness_dir / "state.json").write_text(json.dumps(data))
        store = HarnessDirStateStore()
        state = store.load(tmp_path)
        assert state.epoch == 5
        assert state.completed_tasks == ["t1"]

    def test_returns_defaults_on_malformed(self, tmp_path: Path):
        harness_dir = tmp_path / ".harness"
        harness_dir.mkdir()
        (harness_dir / "state.json").write_text("{bad json")
        store = HarnessDirStateStore()
        state = store.load(tmp_path)
        assert state.epoch == 0


class TestSave:
    def test_creates_harness_dir_and_file(self, tmp_path: Path):
        store = HarnessDirStateStore()
        state = EpochState(epoch=3, completed_tasks=["t1", "t2"])
        store.save(tmp_path, state)
        data = json.loads((tmp_path / ".harness" / "state.json").read_text())
        assert data["epoch"] == 3
        assert data["completed_tasks"] == ["t1", "t2"]
        assert data["_schema_version"] == "1.0"

    def test_overwrites_existing(self, tmp_path: Path):
        store = HarnessDirStateStore()
        store.save(tmp_path, EpochState(epoch=1))
        store.save(tmp_path, EpochState(epoch=2))
        data = json.loads((tmp_path / ".harness" / "state.json").read_text())
        assert data["epoch"] == 2


class TestRoundTrip:
    def test_save_then_load(self, tmp_path: Path):
        store = HarnessDirStateStore()
        original = EpochState(
            epoch=4,
            completed_tasks=["a"],
            pending_tasks=["b"],
            halted=True,
            halt_reason="manual stop",
            metadata={"tag": "test"},
        )
        store.save(tmp_path, original)
        loaded = store.load(tmp_path)
        assert loaded.epoch == original.epoch
        assert loaded.completed_tasks == original.completed_tasks
        assert loaded.pending_tasks == original.pending_tasks
        assert loaded.halted == original.halted
        assert loaded.halt_reason == original.halt_reason
        assert loaded.metadata == original.metadata


class TestProtocolConformance:
    def test_satisfies_state_store_protocol(self):
        from rigger._protocols import StateStore

        store: StateStore = HarnessDirStateStore()
        assert hasattr(store, "load")
        assert hasattr(store, "save")

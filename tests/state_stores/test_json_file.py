"""Tests for JsonFileStateStore."""

from __future__ import annotations

import json
from pathlib import Path

from rigger._types import EpochState
from rigger.state_stores.json_file import JsonFileStateStore


class TestLoad:
    def test_returns_defaults_when_missing(self, tmp_path: Path):
        store = JsonFileStateStore(path="state.json")
        state = store.load(tmp_path)
        assert state.epoch == 0
        assert state.completed_tasks == []
        assert state.pending_tasks == []
        assert state.halted is False

    def test_loads_existing_state(self, tmp_path: Path):
        data = {
            "epoch": 3,
            "completed_tasks": ["t1", "t2"],
            "pending_tasks": ["t3"],
            "halted": False,
            "halt_reason": "",
            "metadata": {"key": "value"},
        }
        (tmp_path / "state.json").write_text(json.dumps(data))
        store = JsonFileStateStore(path="state.json")
        state = store.load(tmp_path)
        assert state.epoch == 3
        assert state.completed_tasks == ["t1", "t2"]
        assert state.pending_tasks == ["t3"]
        assert state.metadata == {"key": "value"}

    def test_returns_defaults_on_malformed_json(self, tmp_path: Path):
        (tmp_path / "state.json").write_text("{not json")
        store = JsonFileStateStore(path="state.json")
        state = store.load(tmp_path)
        assert state.epoch == 0

    def test_returns_defaults_on_non_dict_json(self, tmp_path: Path):
        (tmp_path / "state.json").write_text("[1, 2, 3]")
        store = JsonFileStateStore(path="state.json")
        state = store.load(tmp_path)
        assert state.epoch == 0

    def test_returns_defaults_on_missing_epoch_key(self, tmp_path: Path):
        (tmp_path / "state.json").write_text(json.dumps({"halted": True}))
        store = JsonFileStateStore(path="state.json")
        state = store.load(tmp_path)
        assert state.epoch == 0

    def test_absolute_path(self, tmp_path: Path):
        file_path = tmp_path / "custom" / "state.json"
        file_path.parent.mkdir()
        data = {"epoch": 5, "completed_tasks": [], "pending_tasks": []}
        file_path.write_text(json.dumps(data))
        store = JsonFileStateStore(path=str(file_path))
        state = store.load(tmp_path)
        assert state.epoch == 5


class TestSave:
    def test_creates_file(self, tmp_path: Path):
        store = JsonFileStateStore(path="state.json")
        state = EpochState(epoch=2, completed_tasks=["t1"])
        store.save(tmp_path, state)
        data = json.loads((tmp_path / "state.json").read_text())
        assert data["epoch"] == 2
        assert data["completed_tasks"] == ["t1"]

    def test_creates_parent_directories(self, tmp_path: Path):
        store = JsonFileStateStore(path="sub/dir/state.json")
        store.save(tmp_path, EpochState(epoch=1))
        assert (tmp_path / "sub" / "dir" / "state.json").exists()

    def test_overwrites_existing(self, tmp_path: Path):
        store = JsonFileStateStore(path="state.json")
        store.save(tmp_path, EpochState(epoch=1))
        store.save(tmp_path, EpochState(epoch=2))
        data = json.loads((tmp_path / "state.json").read_text())
        assert data["epoch"] == 2

    def test_preserves_metadata(self, tmp_path: Path):
        store = JsonFileStateStore(path="state.json")
        state = EpochState(epoch=1, metadata={"run_id": "abc123"})
        store.save(tmp_path, state)
        data = json.loads((tmp_path / "state.json").read_text())
        assert data["metadata"]["run_id"] == "abc123"

    def test_halted_state_persisted(self, tmp_path: Path):
        store = JsonFileStateStore(path="state.json")
        state = EpochState(epoch=4, halted=True, halt_reason="BLOCK: lint failed")
        store.save(tmp_path, state)
        data = json.loads((tmp_path / "state.json").read_text())
        assert data["halted"] is True
        assert data["halt_reason"] == "BLOCK: lint failed"


class TestRoundTrip:
    def test_save_then_load(self, tmp_path: Path):
        store = JsonFileStateStore(path="state.json")
        original = EpochState(
            epoch=7,
            completed_tasks=["a", "b"],
            pending_tasks=["c"],
            halted=False,
            halt_reason="",
            metadata={"retries": 3},
        )
        store.save(tmp_path, original)
        loaded = store.load(tmp_path)
        assert loaded.epoch == original.epoch
        assert loaded.completed_tasks == original.completed_tasks
        assert loaded.pending_tasks == original.pending_tasks
        assert loaded.halted == original.halted
        assert loaded.halt_reason == original.halt_reason
        assert loaded.metadata == original.metadata

    def test_mark_complete_idempotency(self, tmp_path: Path):
        store = JsonFileStateStore(path="state.json")
        state = EpochState(epoch=1, completed_tasks=["t1"])
        store.save(tmp_path, state)
        store.save(tmp_path, state)
        loaded = store.load(tmp_path)
        assert loaded.completed_tasks == ["t1"]


class TestProtocolConformance:
    def test_satisfies_state_store_protocol(self):
        from rigger._protocols import StateStore

        store: StateStore = JsonFileStateStore(path="state.json")
        assert hasattr(store, "load")
        assert hasattr(store, "save")

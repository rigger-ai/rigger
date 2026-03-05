"""Tests for rigger._schema — .harness/ bilateral protocol utilities."""

import json

import pytest

from rigger._schema import (
    CONSTRAINTS_FILE,
    ENTROPY_DIR,
    HARNESS_DIR,
    SCHEMA_VERSION,
    STATE_FILE,
    TASK_FILE,
    FilesystemEntropyTaskSource,
    ensure_harness_dir,
    read_constraints,
    read_current_task,
    read_state,
    write_constraints,
    write_current_task,
    write_entropy_tasks,
    write_state,
)
from rigger._types import EpochState, Task

# ─── ensure_harness_dir ─────────────────────────────────────


class TestEnsureHarnessDir:
    def test_creates_directory(self, tmp_path):
        result = ensure_harness_dir(tmp_path)
        assert result == tmp_path / HARNESS_DIR
        assert result.is_dir()

    def test_idempotent(self, tmp_path):
        ensure_harness_dir(tmp_path)
        ensure_harness_dir(tmp_path)
        assert (tmp_path / HARNESS_DIR).is_dir()


# ─── write/read current_task round-trip ──────────────────────


class TestCurrentTask:
    def test_round_trip(self, tmp_path):
        task = Task(
            id="feat-42",
            description="Add pagination",
            metadata={"priority": 1},
        )
        write_current_task(tmp_path, task)
        result = read_current_task(tmp_path)
        assert result is not None
        assert result.id == task.id
        assert result.description == task.description
        assert result.metadata == task.metadata

    def test_round_trip_default_metadata(self, tmp_path):
        task = Task(id="t1", description="desc")
        write_current_task(tmp_path, task)
        result = read_current_task(tmp_path)
        assert result is not None
        assert result.metadata == {}

    def test_includes_schema_version(self, tmp_path):
        write_current_task(tmp_path, Task(id="t1", description="d"))
        data = json.loads((tmp_path / HARNESS_DIR / TASK_FILE).read_text())
        assert data["_schema_version"] == SCHEMA_VERSION

    def test_creates_harness_dir(self, tmp_path):
        write_current_task(tmp_path, Task(id="t1", description="d"))
        assert (tmp_path / HARNESS_DIR).is_dir()

    def test_missing_returns_none(self, tmp_path):
        assert read_current_task(tmp_path) is None

    def test_malformed_json_returns_none(self, tmp_path):
        harness_dir = tmp_path / HARNESS_DIR
        harness_dir.mkdir()
        (harness_dir / TASK_FILE).write_text("{{not valid json")
        assert read_current_task(tmp_path) is None

    def test_json_array_returns_none(self, tmp_path):
        harness_dir = tmp_path / HARNESS_DIR
        harness_dir.mkdir()
        (harness_dir / TASK_FILE).write_text("[1, 2, 3]")
        assert read_current_task(tmp_path) is None

    def test_missing_id_returns_none(self, tmp_path):
        harness_dir = tmp_path / HARNESS_DIR
        harness_dir.mkdir()
        data = {"_schema_version": "1.0", "description": "no id"}
        (harness_dir / TASK_FILE).write_text(json.dumps(data))
        assert read_current_task(tmp_path) is None

    def test_missing_description_returns_none(self, tmp_path):
        harness_dir = tmp_path / HARNESS_DIR
        harness_dir.mkdir()
        data = {"_schema_version": "1.0", "id": "t1"}
        (harness_dir / TASK_FILE).write_text(json.dumps(data))
        assert read_current_task(tmp_path) is None

    def test_unknown_major_version_still_works(self, tmp_path):
        harness_dir = tmp_path / HARNESS_DIR
        harness_dir.mkdir()
        data = {"_schema_version": "2.0", "id": "t1", "description": "d"}
        (harness_dir / TASK_FILE).write_text(json.dumps(data))
        result = read_current_task(tmp_path)
        assert result is not None
        assert result.id == "t1"

    def test_ignores_unknown_fields(self, tmp_path):
        harness_dir = tmp_path / HARNESS_DIR
        harness_dir.mkdir()
        data = {
            "_schema_version": "1.0",
            "id": "t1",
            "description": "d",
            "future_field": "ignored",
        }
        (harness_dir / TASK_FILE).write_text(json.dumps(data))
        result = read_current_task(tmp_path)
        assert result is not None
        assert result.id == "t1"


# ─── write/read state round-trip ─────────────────────────────


class TestState:
    def test_round_trip(self, tmp_path):
        state = EpochState(
            epoch=5,
            completed_tasks=["t1", "t2"],
            pending_tasks=["t3"],
            metadata={"last_result_status": "success"},
        )
        write_state(tmp_path, state)
        result = read_state(tmp_path)
        assert result.epoch == state.epoch
        assert result.completed_tasks == state.completed_tasks
        assert result.pending_tasks == state.pending_tasks
        assert result.metadata == state.metadata

    def test_round_trip_defaults(self, tmp_path):
        state = EpochState()
        write_state(tmp_path, state)
        result = read_state(tmp_path)
        assert result.epoch == 0
        assert result.completed_tasks == []
        assert result.pending_tasks == []

    def test_includes_schema_version(self, tmp_path):
        write_state(tmp_path, EpochState(epoch=1))
        data = json.loads((tmp_path / HARNESS_DIR / STATE_FILE).read_text())
        assert data["_schema_version"] == SCHEMA_VERSION

    def test_missing_returns_default(self, tmp_path):
        result = read_state(tmp_path)
        assert result.epoch == 0
        assert result.completed_tasks == []
        assert result.pending_tasks == []
        assert result.metadata == {}

    def test_malformed_json_returns_default(self, tmp_path):
        harness_dir = tmp_path / HARNESS_DIR
        harness_dir.mkdir()
        (harness_dir / STATE_FILE).write_text("not json at all")
        result = read_state(tmp_path)
        assert result.epoch == 0

    def test_json_string_returns_default(self, tmp_path):
        harness_dir = tmp_path / HARNESS_DIR
        harness_dir.mkdir()
        (harness_dir / STATE_FILE).write_text('"just a string"')
        result = read_state(tmp_path)
        assert result.epoch == 0

    def test_missing_epoch_returns_default(self, tmp_path):
        harness_dir = tmp_path / HARNESS_DIR
        harness_dir.mkdir()
        data = {"_schema_version": "1.0", "completed_tasks": ["t1"]}
        (harness_dir / STATE_FILE).write_text(json.dumps(data))
        result = read_state(tmp_path)
        assert result.epoch == 0

    def test_unknown_minor_version_works(self, tmp_path):
        harness_dir = tmp_path / HARNESS_DIR
        harness_dir.mkdir()
        data = {
            "_schema_version": "1.3",
            "epoch": 5,
            "completed_tasks": ["t1"],
            "new_future_field": "ignored",
        }
        (harness_dir / STATE_FILE).write_text(json.dumps(data))
        result = read_state(tmp_path)
        assert result.epoch == 5
        assert result.completed_tasks == ["t1"]


# ─── write/read constraints round-trip ───────────────────────


class TestConstraints:
    def test_round_trip(self, tmp_path):
        metadata = {
            "allowed_tools": ["mcp__bash__run"],
            "disallowed_tools": ["curl", "rm"],
            "max_iterations": 30,
        }
        write_constraints(tmp_path, metadata)
        result = read_constraints(tmp_path)
        assert result == metadata

    def test_includes_schema_version(self, tmp_path):
        write_constraints(tmp_path, {"disallowed_tools": ["rm"]})
        data = json.loads((tmp_path / HARNESS_DIR / CONSTRAINTS_FILE).read_text())
        assert data["_schema_version"] == SCHEMA_VERSION

    def test_strips_schema_version_on_read(self, tmp_path):
        write_constraints(tmp_path, {"max_iterations": 10})
        result = read_constraints(tmp_path)
        assert "_schema_version" not in result

    def test_empty_deletes_stale_file(self, tmp_path):
        write_constraints(tmp_path, {"disallowed_tools": ["rm"]})
        constraints_path = tmp_path / HARNESS_DIR / CONSTRAINTS_FILE
        assert constraints_path.exists()
        write_constraints(tmp_path, {})
        assert not constraints_path.exists()

    def test_empty_noop_if_no_file(self, tmp_path):
        write_constraints(tmp_path, {})  # Should not raise

    def test_missing_returns_empty_dict(self, tmp_path):
        assert read_constraints(tmp_path) == {}

    def test_malformed_json_returns_empty(self, tmp_path):
        harness_dir = tmp_path / HARNESS_DIR
        harness_dir.mkdir()
        (harness_dir / CONSTRAINTS_FILE).write_text("[broken")
        assert read_constraints(tmp_path) == {}

    def test_preserves_custom_vendor_keys(self, tmp_path):
        metadata = {
            "disallowed_tools": ["rm"],
            "acme.require_signed_commits": True,
        }
        write_constraints(tmp_path, metadata)
        result = read_constraints(tmp_path)
        assert result["acme.require_signed_commits"] is True


# ─── Atomic write behavior ───────────────────────────────────


class TestAtomicWrite:
    def test_no_temp_files_left(self, tmp_path):
        write_current_task(tmp_path, Task(id="t1", description="d"))
        harness_dir = tmp_path / HARNESS_DIR
        tmp_files = list(harness_dir.glob(".tmp_*"))
        assert tmp_files == []

    def test_all_files_valid_json(self, tmp_path):
        write_current_task(tmp_path, Task(id="t1", description="d"))
        write_state(tmp_path, EpochState(epoch=3))
        write_constraints(tmp_path, {"max_iterations": 5})
        for filename in [TASK_FILE, STATE_FILE, CONSTRAINTS_FILE]:
            path = tmp_path / HARNESS_DIR / filename
            data = json.loads(path.read_text())
            assert isinstance(data, dict)

    def test_overwrite_existing_file(self, tmp_path):
        write_current_task(tmp_path, Task(id="t1", description="first"))
        write_current_task(tmp_path, Task(id="t2", description="second"))
        result = read_current_task(tmp_path)
        assert result is not None
        assert result.id == "t2"
        assert result.description == "second"


# ─── write_entropy_tasks ────────────────────────────────────


class TestWriteEntropyTasks:
    def test_happy_path(self, tmp_path):
        tasks = [Task(id="e1", description="fix drift")]
        path = write_entropy_tasks(tmp_path, tasks)
        assert path.exists()
        assert path.parent == tmp_path / HARNESS_DIR / ENTROPY_DIR
        assert path.name.startswith("tasks_")
        data = json.loads(path.read_text())
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["id"] == "e1"

    def test_multiple_tasks(self, tmp_path):
        tasks = [
            Task(id="e1", description="d1"),
            Task(id="e2", description="d2", metadata={"prio": 1}),
        ]
        path = write_entropy_tasks(tmp_path, tasks)
        data = json.loads(path.read_text())
        assert len(data["tasks"]) == 2
        assert data["tasks"][1]["metadata"] == {"prio": 1}

    def test_empty_raises_valueerror(self, tmp_path):
        with pytest.raises(ValueError, match="empty"):
            write_entropy_tasks(tmp_path, [])

    def test_atomic_no_temp_files(self, tmp_path):
        write_entropy_tasks(tmp_path, [Task(id="e1", description="d")])
        entropy_dir = tmp_path / HARNESS_DIR / ENTROPY_DIR
        tmp_files = list(entropy_dir.glob(".tmp_*"))
        assert tmp_files == []

    def test_schema_version_included(self, tmp_path):
        path = write_entropy_tasks(tmp_path, [Task(id="e1", description="d")])
        data = json.loads(path.read_text())
        assert data["tasks"][0]["_schema_version"] == SCHEMA_VERSION


# ─── FilesystemEntropyTaskSource ─────────────────────────────


class TestFilesystemEntropyTaskSource:
    def test_pending_reads_partitions(self, tmp_path):
        write_entropy_tasks(tmp_path, [Task(id="e1", description="d1")])
        write_entropy_tasks(tmp_path, [Task(id="e2", description="d2")])
        source = FilesystemEntropyTaskSource(tmp_path)
        tasks = source.pending(tmp_path)
        ids = [t.id for t in tasks]
        assert "e1" in ids
        assert "e2" in ids

    def test_pending_empty_dir(self, tmp_path):
        source = FilesystemEntropyTaskSource(tmp_path)
        assert source.pending(tmp_path) == []

    def test_mark_complete_removes_task(self, tmp_path):
        write_entropy_tasks(
            tmp_path,
            [Task(id="e1", description="d1"), Task(id="e2", description="d2")],
        )
        source = FilesystemEntropyTaskSource(tmp_path)
        assert len(source.pending(tmp_path)) == 2
        source.mark_complete("e1")
        remaining = source.pending(tmp_path)
        assert len(remaining) == 1
        assert remaining[0].id == "e2"

    def test_mark_complete_deletes_empty_partition(self, tmp_path):
        write_entropy_tasks(tmp_path, [Task(id="e1", description="d1")])
        source = FilesystemEntropyTaskSource(tmp_path)
        source.mark_complete("e1")
        entropy_dir = tmp_path / HARNESS_DIR / ENTROPY_DIR
        partitions = list(entropy_dir.glob("tasks_*.json"))
        assert partitions == []

    def test_legacy_migration(self, tmp_path):
        """pending_tasks.json is migrated to partitioned format."""
        harness_dir = tmp_path / HARNESS_DIR
        harness_dir.mkdir(parents=True)
        legacy = [
            {"id": "leg1", "description": "legacy task 1"},
            {"id": "leg2", "description": "legacy task 2", "metadata": {"k": "v"}},
        ]
        (harness_dir / "pending_tasks.json").write_text(json.dumps(legacy))

        source = FilesystemEntropyTaskSource(tmp_path)
        tasks = source.pending(tmp_path)
        assert len(tasks) == 2
        assert tasks[0].id == "leg1"
        assert tasks[1].metadata == {"k": "v"}
        # Legacy file should be removed
        assert not (harness_dir / "pending_tasks.json").exists()

    def test_orphan_cleanup(self, tmp_path):
        """Orphaned .tmp_* files are cleaned up on init."""
        entropy_dir = tmp_path / HARNESS_DIR / ENTROPY_DIR
        entropy_dir.mkdir(parents=True)
        orphan = entropy_dir / ".tmp_abcdef.json"
        orphan.write_text("{}")
        FilesystemEntropyTaskSource(tmp_path)
        assert not orphan.exists()

    def test_malformed_partition_skipped(self, tmp_path):
        """Malformed partition files are skipped gracefully."""
        entropy_dir = tmp_path / HARNESS_DIR / ENTROPY_DIR
        entropy_dir.mkdir(parents=True)
        (entropy_dir / "tasks_0001_abc.json").write_text("not json")
        write_entropy_tasks(tmp_path, [Task(id="e1", description="d1")])
        source = FilesystemEntropyTaskSource(tmp_path)
        tasks = source.pending(tmp_path)
        assert len(tasks) == 1
        assert tasks[0].id == "e1"

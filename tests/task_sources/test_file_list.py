"""Tests for FileListTaskSource."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rigger._types import TaskResult
from rigger.task_sources.file_list import FileListTaskSource


@pytest.fixture
def tasks_json(tmp_path: Path) -> Path:
    data = [
        {"id": "t1", "description": "Add login page", "status": "pending"},
        {"id": "t2", "description": "Add tests", "status": "done"},
        {"id": "t3", "description": "Fix bug", "status": "pending", "priority": 1},
    ]
    p = tmp_path / "tasks.json"
    p.write_text(json.dumps(data))
    return p


class TestPending:
    def test_returns_pending_tasks(self, tasks_json: Path, tmp_path: Path):
        src = FileListTaskSource(path=str(tasks_json))
        tasks = src.pending(tmp_path)
        assert len(tasks) == 2
        assert tasks[0].id == "t1"
        assert tasks[1].id == "t3"

    def test_preserves_metadata(self, tasks_json: Path, tmp_path: Path):
        src = FileListTaskSource(path=str(tasks_json))
        tasks = src.pending(tmp_path)
        assert tasks[1].metadata["priority"] == 1

    def test_empty_file(self, tmp_path: Path):
        p = tmp_path / "tasks.json"
        p.write_text("[]")
        src = FileListTaskSource(path=str(p))
        assert src.pending(tmp_path) == []

    def test_missing_file(self, tmp_path: Path):
        src = FileListTaskSource(path="nonexistent.json")
        assert src.pending(tmp_path) == []

    def test_malformed_json(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("{not json")
        src = FileListTaskSource(path=str(p))
        assert src.pending(tmp_path) == []

    def test_non_array_json(self, tmp_path: Path):
        p = tmp_path / "obj.json"
        p.write_text('{"tasks": []}')
        src = FileListTaskSource(path=str(p))
        assert src.pending(tmp_path) == []

    def test_skips_items_without_id(self, tmp_path: Path):
        p = tmp_path / "tasks.json"
        items = [{"description": "no id"}, {"id": "t1", "description": "ok"}]
        p.write_text(json.dumps(items))
        src = FileListTaskSource(path=str(p))
        tasks = src.pending(tmp_path)
        assert len(tasks) == 1
        assert tasks[0].id == "t1"

    def test_default_status_is_pending(self, tmp_path: Path):
        p = tmp_path / "tasks.json"
        p.write_text(json.dumps([{"id": "t1", "description": "no status field"}]))
        src = FileListTaskSource(path=str(p))
        tasks = src.pending(tmp_path)
        assert len(tasks) == 1

    def test_relative_path(self, tmp_path: Path):
        data = [{"id": "t1", "description": "x"}]
        (tmp_path / "tasks.json").write_text(json.dumps(data))
        src = FileListTaskSource(path="tasks.json")
        tasks = src.pending(tmp_path)
        assert len(tasks) == 1


class TestMarkComplete:
    def test_updates_status_to_done(self, tasks_json: Path, tmp_path: Path):
        src = FileListTaskSource(path=str(tasks_json))
        result = TaskResult(task_id="t1", status="success")
        src.mark_complete("t1", result)

        data = json.loads(tasks_json.read_text())
        assert data[0]["status"] == "done"

    def test_idempotent(self, tasks_json: Path, tmp_path: Path):
        src = FileListTaskSource(path=str(tasks_json))
        result = TaskResult(task_id="t1", status="success")
        src.mark_complete("t1", result)
        src.mark_complete("t1", result)

        data = json.loads(tasks_json.read_text())
        assert data[0]["status"] == "done"

    def test_unknown_task_id_noop(self, tasks_json: Path, tmp_path: Path):
        src = FileListTaskSource(path=str(tasks_json))
        result = TaskResult(task_id="unknown", status="success")
        src.mark_complete("unknown", result)
        # Should not raise, other tasks unchanged
        data = json.loads(tasks_json.read_text())
        assert data[0]["status"] == "pending"

    def test_after_complete_task_disappears(self, tasks_json: Path, tmp_path: Path):
        src = FileListTaskSource(path=str(tasks_json))
        result = TaskResult(task_id="t1", status="success")
        src.mark_complete("t1", result)
        tasks = src.pending(tmp_path)
        ids = [t.id for t in tasks]
        assert "t1" not in ids

    def test_atomic_write_preserves_other_data(self, tasks_json: Path, tmp_path: Path):
        src = FileListTaskSource(path=str(tasks_json))
        result = TaskResult(task_id="t3", status="success")
        src.mark_complete("t3", result)

        data = json.loads(tasks_json.read_text())
        # t2 was already done, t1 still pending
        assert data[1]["status"] == "done"
        assert data[0]["status"] == "pending"
        # t3 marked done, priority preserved
        assert data[2]["status"] == "done"
        assert data[2]["priority"] == 1


class TestProtocolConformance:
    def test_satisfies_task_source_protocol(self):
        from rigger._protocols import TaskSource

        source: TaskSource = FileListTaskSource(path="x.json")
        assert hasattr(source, "pending")
        assert hasattr(source, "mark_complete")

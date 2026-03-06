"""Integration tests for TaskSource implementations against real filesystems."""

from __future__ import annotations

import json
import os

from rigger._types import EpochState, TaskResult
from rigger.state_stores import JsonFileStateStore
from rigger.task_sources import FileListTaskSource, JsonStoriesTaskSource


def test_file_list_reads_and_marks_complete(task_file, git_project):
    ts = FileListTaskSource(path="tasks.json")

    pending = ts.pending(git_project)
    assert len(pending) == 3
    assert [t.id for t in pending] == ["t1", "t2", "t3"]

    original_cwd = os.getcwd()
    try:
        os.chdir(git_project)
        ts.mark_complete("t1", TaskResult(task_id="t1", status="success"))
    finally:
        os.chdir(original_cwd)

    data = json.loads((git_project / "tasks.json").read_text())
    t1 = next(t for t in data if t["id"] == "t1")
    assert t1["status"] == "done"

    pending = ts.pending(git_project)
    assert len(pending) == 2
    assert [t.id for t in pending] == ["t2", "t3"]


def test_json_stories_reads_and_marks_complete(stories_file, git_project):
    ts = JsonStoriesTaskSource(path="stories.json")

    pending = ts.pending(git_project)
    assert len(pending) == 1
    assert pending[0].id == "s1"

    original_cwd = os.getcwd()
    try:
        os.chdir(git_project)
        ts.mark_complete("s1", TaskResult(task_id="s1", status="success"))
    finally:
        os.chdir(original_cwd)

    pending = ts.pending(git_project)
    assert len(pending) == 1
    assert pending[0].id == "s2"


def test_file_list_roundtrip_with_state_store(task_file, git_project):
    ts = FileListTaskSource(path="tasks.json")
    store = JsonFileStateStore(path="state.json")

    pending = ts.pending(git_project)
    assert len(pending) == 3

    state = EpochState(epoch=1, completed_tasks=["t1"])
    store.save(git_project, state)

    loaded = store.load(git_project)
    assert loaded.epoch == 1
    assert loaded.completed_tasks == ["t1"]

    original_cwd = os.getcwd()
    try:
        os.chdir(git_project)
        ts.mark_complete("t1", TaskResult(task_id="t1", status="success"))
    finally:
        os.chdir(original_cwd)

    pending = ts.pending(git_project)
    assert len(pending) == 2
    assert [t.id for t in pending] == ["t2", "t3"]

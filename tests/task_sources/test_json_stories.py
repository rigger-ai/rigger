"""Tests for JsonStoriesTaskSource."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rigger._types import TaskResult
from rigger.task_sources.json_stories import JsonStoriesTaskSource


@pytest.fixture
def stories_json(tmp_path: Path) -> Path:
    data = {
        "stories": [
            {"id": "s1", "description": "User can sign up", "status": "pending"},
            {"id": "s2", "description": "User can log in", "status": "done"},
            {
                "id": "s3",
                "description": "User can reset password",
                "acceptance_criteria": ["Email sent", "Link works"],
            },
        ]
    }
    p = tmp_path / "prd.json"
    p.write_text(json.dumps(data))
    return p


class TestPending:
    def test_returns_first_pending_story(self, stories_json: Path, tmp_path: Path):
        src = JsonStoriesTaskSource(path=str(stories_json))
        tasks = src.pending(tmp_path)
        assert len(tasks) == 1
        assert tasks[0].id == "s1"
        assert tasks[0].description == "User can sign up"

    def test_skips_done_stories(self, stories_json: Path, tmp_path: Path):
        # Mark s1 as done in the file
        data = json.loads(stories_json.read_text())
        data["stories"][0]["status"] = "done"
        stories_json.write_text(json.dumps(data))

        src = JsonStoriesTaskSource(path=str(stories_json))
        tasks = src.pending(tmp_path)
        assert len(tasks) == 1
        assert tasks[0].id == "s3"  # s2 is done, s3 has no status (defaults pending)

    def test_preserves_extra_metadata(self, stories_json: Path, tmp_path: Path):
        # Mark s1 as done to get to s3 which has acceptance_criteria
        data = json.loads(stories_json.read_text())
        data["stories"][0]["status"] = "done"
        stories_json.write_text(json.dumps(data))

        src = JsonStoriesTaskSource(path=str(stories_json))
        tasks = src.pending(tmp_path)
        assert tasks[0].id == "s3"
        assert tasks[0].metadata["acceptance_criteria"] == ["Email sent", "Link works"]

    def test_empty_stories(self, tmp_path: Path):
        p = tmp_path / "prd.json"
        p.write_text(json.dumps({"stories": []}))
        src = JsonStoriesTaskSource(path=str(p))
        assert src.pending(tmp_path) == []

    def test_missing_file(self, tmp_path: Path):
        src = JsonStoriesTaskSource(path="nonexistent.json")
        assert src.pending(tmp_path) == []

    def test_malformed_json(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("{bad json")
        src = JsonStoriesTaskSource(path=str(p))
        assert src.pending(tmp_path) == []

    def test_custom_key(self, tmp_path: Path):
        data = {"features": [{"id": "f1", "description": "Feature one"}]}
        p = tmp_path / "features.json"
        p.write_text(json.dumps(data))
        src = JsonStoriesTaskSource(path=str(p), key="features")
        tasks = src.pending(tmp_path)
        assert len(tasks) == 1
        assert tasks[0].id == "f1"

    def test_wrong_key_returns_empty(self, tmp_path: Path):
        data = {"stories": [{"id": "s1", "description": "x"}]}
        p = tmp_path / "prd.json"
        p.write_text(json.dumps(data))
        src = JsonStoriesTaskSource(path=str(p), key="features")
        assert src.pending(tmp_path) == []

    def test_non_object_file(self, tmp_path: Path):
        p = tmp_path / "prd.json"
        p.write_text(json.dumps([1, 2, 3]))
        src = JsonStoriesTaskSource(path=str(p))
        assert src.pending(tmp_path) == []

    def test_skips_items_without_id(self, tmp_path: Path):
        data = {
            "stories": [
                {"description": "no id"},
                {"id": "s1", "description": "ok"},
            ]
        }
        p = tmp_path / "prd.json"
        p.write_text(json.dumps(data))
        src = JsonStoriesTaskSource(path=str(p))
        tasks = src.pending(tmp_path)
        assert len(tasks) == 1
        assert tasks[0].id == "s1"

    def test_story_field_alias(self, tmp_path: Path):
        data = {"stories": [{"id": "s1", "story": "As a user I want to login"}]}
        p = tmp_path / "prd.json"
        p.write_text(json.dumps(data))
        src = JsonStoriesTaskSource(path=str(p))
        tasks = src.pending(tmp_path)
        assert tasks[0].description == "As a user I want to login"

    def test_relative_path(self, tmp_path: Path):
        data = {"stories": [{"id": "s1", "description": "x"}]}
        (tmp_path / "prd.json").write_text(json.dumps(data))
        src = JsonStoriesTaskSource(path="prd.json")
        tasks = src.pending(tmp_path)
        assert len(tasks) == 1


class TestMarkComplete:
    def test_updates_status_to_done(self, stories_json: Path, tmp_path: Path):
        src = JsonStoriesTaskSource(path=str(stories_json))
        result = TaskResult(task_id="s1", status="success")
        src.mark_complete("s1", result)

        data = json.loads(stories_json.read_text())
        assert data["stories"][0]["status"] == "done"

    def test_idempotent(self, stories_json: Path, tmp_path: Path):
        src = JsonStoriesTaskSource(path=str(stories_json))
        result = TaskResult(task_id="s1", status="success")
        src.mark_complete("s1", result)
        src.mark_complete("s1", result)

        data = json.loads(stories_json.read_text())
        assert data["stories"][0]["status"] == "done"

    def test_unknown_task_id_noop(self, stories_json: Path, tmp_path: Path):
        src = JsonStoriesTaskSource(path=str(stories_json))
        result = TaskResult(task_id="unknown", status="success")
        src.mark_complete("unknown", result)
        data = json.loads(stories_json.read_text())
        assert data["stories"][0]["status"] == "pending"

    def test_after_complete_next_story_returned(
        self, stories_json: Path, tmp_path: Path
    ):
        src = JsonStoriesTaskSource(path=str(stories_json))
        result = TaskResult(task_id="s1", status="success")
        src.mark_complete("s1", result)
        tasks = src.pending(tmp_path)
        assert len(tasks) == 1
        assert tasks[0].id == "s3"  # s2 was already done

    def test_preserves_other_data(self, stories_json: Path, tmp_path: Path):
        src = JsonStoriesTaskSource(path=str(stories_json))
        result = TaskResult(task_id="s3", status="success")
        src.mark_complete("s3", result)

        data = json.loads(stories_json.read_text())
        assert data["stories"][2]["acceptance_criteria"] == ["Email sent", "Link works"]


class TestProtocolConformance:
    def test_satisfies_task_source_protocol(self):
        from rigger._protocols import TaskSource

        source: TaskSource = JsonStoriesTaskSource(path="x.json")
        assert hasattr(source, "pending")
        assert hasattr(source, "mark_complete")

"""Tests for IndependentDirManager — workspace isolation via directory copies."""

from __future__ import annotations

from pathlib import Path

import pytest

from rigger._types import MergeResult, Task
from rigger.workspace.independent import IndependentDirManager


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal project directory with some files."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("# Test\n")
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text("print('hello')\n")
    return project


@pytest.fixture
def manager() -> IndependentDirManager:
    return IndependentDirManager()


@pytest.fixture
def task() -> Task:
    return Task(id="t1", description="Test task")


class TestCreate:
    def test_creates_workspace_directory(
        self, project_dir: Path, manager: IndependentDirManager, task: Task
    ):
        ws = manager.create(project_dir, task, "unused-branch")
        assert ws.exists()
        assert ws.is_dir()

    def test_workspace_has_project_files(
        self, project_dir: Path, manager: IndependentDirManager, task: Task
    ):
        ws = manager.create(project_dir, task, "unused-branch")
        assert (ws / "README.md").exists()
        assert (ws / "README.md").read_text() == "# Test\n"
        assert (ws / "src" / "main.py").exists()
        assert (ws / "src" / "main.py").read_text() == "print('hello')\n"

    def test_workspace_is_independent_copy(
        self, project_dir: Path, manager: IndependentDirManager, task: Task
    ):
        ws = manager.create(project_dir, task, "unused-branch")
        # Modify the workspace — original should be untouched.
        (ws / "README.md").write_text("# Modified\n")
        assert (project_dir / "README.md").read_text() == "# Test\n"

    def test_workspace_preserves_directory_name(
        self, project_dir: Path, manager: IndependentDirManager, task: Task
    ):
        ws = manager.create(project_dir, task, "unused-branch")
        assert ws.name == project_dir.name

    def test_multiple_workspaces_are_independent(
        self, project_dir: Path, manager: IndependentDirManager
    ):
        t1 = Task(id="t1", description="Task 1")
        t2 = Task(id="t2", description="Task 2")
        ws1 = manager.create(project_dir, t1, "branch-1")
        ws2 = manager.create(project_dir, t2, "branch-2")
        assert ws1 != ws2
        (ws1 / "README.md").write_text("# From ws1\n")
        assert (ws2 / "README.md").read_text() == "# Test\n"


class TestMerge:
    def test_merge_copies_back(
        self, project_dir: Path, manager: IndependentDirManager, task: Task
    ):
        ws = manager.create(project_dir, task, "unused-branch")
        (ws / "new_file.txt").write_text("hello\n")
        result = manager.merge(ws, project_dir)
        assert isinstance(result, MergeResult)
        assert result.success is True
        assert (project_dir / "new_file.txt").exists()
        assert (project_dir / "new_file.txt").read_text() == "hello\n"

    def test_merge_overwrites_existing(
        self, project_dir: Path, manager: IndependentDirManager, task: Task
    ):
        ws = manager.create(project_dir, task, "unused-branch")
        (ws / "README.md").write_text("# Updated\n")
        result = manager.merge(ws, project_dir)
        assert result.success is True
        assert (project_dir / "README.md").read_text() == "# Updated\n"

    def test_merge_returns_worktree_path(
        self, project_dir: Path, manager: IndependentDirManager, task: Task
    ):
        ws = manager.create(project_dir, task, "unused-branch")
        result = manager.merge(ws, project_dir)
        assert result.worktree_path == ws


class TestCleanup:
    def test_cleanup_removes_workspace(
        self, project_dir: Path, manager: IndependentDirManager, task: Task
    ):
        ws = manager.create(project_dir, task, "unused-branch")
        assert ws.exists()
        manager.cleanup(ws)
        assert not ws.exists()
        assert not ws.parent.exists()  # Temp parent is also removed.

    def test_cleanup_idempotent(
        self, project_dir: Path, manager: IndependentDirManager, task: Task
    ):
        ws = manager.create(project_dir, task, "unused-branch")
        manager.cleanup(ws)
        # Second cleanup should not raise.
        manager.cleanup(ws)


class TestFullLifecycle:
    def test_create_modify_merge_cleanup(
        self, project_dir: Path, manager: IndependentDirManager, task: Task
    ):
        # Create.
        ws = manager.create(project_dir, task, "unused-branch")
        assert ws.exists()

        # Modify.
        (ws / "output.txt").write_text("result\n")

        # Merge.
        result = manager.merge(ws, project_dir)
        assert result.success is True
        assert (project_dir / "output.txt").read_text() == "result\n"

        # Cleanup.
        manager.cleanup(ws)
        assert not ws.exists()

    def test_custom_prefix(self, project_dir: Path, task: Task):
        mgr = IndependentDirManager(prefix="custom-test-")
        ws = mgr.create(project_dir, task, "unused-branch")
        assert "custom-test-" in str(ws.parent)
        mgr.cleanup(ws)

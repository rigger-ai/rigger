"""Tests for GitWorktreeManager — workspace isolation via git worktrees."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rigger._types import MergeResult, Task
from rigger.workspace.git_worktree import GitWorktreeManager


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repository with one commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


@pytest.fixture
def manager() -> GitWorktreeManager:
    return GitWorktreeManager()


@pytest.fixture
def task() -> Task:
    return Task(id="t1", description="Test task")


class TestCreate:
    def test_creates_worktree_directory(
        self, git_repo: Path, manager: GitWorktreeManager, task: Task
    ):
        wt = manager.create(git_repo, task, "rigger/test/t1")
        assert wt.exists()
        assert wt.is_dir()
        # Worktree has a .git file (not directory) pointing to main repo.
        assert (wt / ".git").exists()

    def test_returns_path_under_rigger_worktrees(
        self, git_repo: Path, manager: GitWorktreeManager, task: Task
    ):
        wt = manager.create(git_repo, task, "rigger/test/t1")
        assert ".rigger-worktrees" in str(wt)

    def test_worktree_has_repo_files(
        self, git_repo: Path, manager: GitWorktreeManager, task: Task
    ):
        wt = manager.create(git_repo, task, "rigger/test/t1")
        assert (wt / "README.md").exists()
        assert (wt / "README.md").read_text() == "# Test\n"

    def test_worktree_is_on_correct_branch(
        self, git_repo: Path, manager: GitWorktreeManager, task: Task
    ):
        wt = manager.create(git_repo, task, "rigger/test/t1")
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=wt,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "rigger/test/t1"

    def test_stale_worktree_is_cleaned_up(
        self, git_repo: Path, manager: GitWorktreeManager, task: Task
    ):
        # Create first, then create again with same branch name.
        wt1 = manager.create(git_repo, task, "rigger/test/t1")
        assert wt1.exists()
        wt2 = manager.create(git_repo, task, "rigger/test/t1")
        assert wt2.exists()
        assert wt1 == wt2  # Same path, recreated.

    def test_empty_repo_raises(self, tmp_path: Path, manager: GitWorktreeManager):
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        task = Task(id="t1", description="Test")
        with pytest.raises(RuntimeError, match="no commits"):
            manager.create(repo, task, "rigger/test/t1")


class TestMerge:
    def test_merge_success(
        self, git_repo: Path, manager: GitWorktreeManager, task: Task
    ):
        wt = manager.create(git_repo, task, "rigger/test/t1")
        # Make a change in the worktree and commit.
        (wt / "new_file.txt").write_text("hello\n")
        subprocess.run(["git", "add", "."], cwd=wt, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add file"],
            cwd=wt,
            check=True,
            capture_output=True,
        )
        result = manager.merge(wt, git_repo)
        assert isinstance(result, MergeResult)
        assert result.success is True
        # File should now exist in main repo.
        assert (git_repo / "new_file.txt").exists()

    def test_merge_conflict(
        self, git_repo: Path, manager: GitWorktreeManager, task: Task
    ):
        wt = manager.create(git_repo, task, "rigger/test/t1")
        # Modify README in worktree.
        (wt / "README.md").write_text("# Changed in worktree\n")
        subprocess.run(["git", "add", "."], cwd=wt, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "wt change"],
            cwd=wt,
            check=True,
            capture_output=True,
        )
        # Modify same file in main repo.
        (git_repo / "README.md").write_text("# Changed in main\n")
        subprocess.run(
            ["git", "add", "."], cwd=git_repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "main change"],
            cwd=git_repo,
            check=True,
            capture_output=True,
        )
        result = manager.merge(wt, git_repo)
        assert result.success is False
        assert result.worktree_path == wt

    def test_merge_no_changes_succeeds(
        self, git_repo: Path, manager: GitWorktreeManager, task: Task
    ):
        wt = manager.create(git_repo, task, "rigger/test/t1")
        # Make an empty commit to avoid "Already up to date" failure.
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "empty"],
            cwd=wt,
            check=True,
            capture_output=True,
        )
        result = manager.merge(wt, git_repo)
        assert result.success is True


class TestCleanup:
    def test_cleanup_removes_worktree(
        self, git_repo: Path, manager: GitWorktreeManager, task: Task
    ):
        wt = manager.create(git_repo, task, "rigger/test/t1")
        assert wt.exists()
        manager.cleanup(wt)
        assert not wt.exists()

    def test_cleanup_removes_branch(
        self, git_repo: Path, manager: GitWorktreeManager, task: Task
    ):
        manager.create(git_repo, task, "rigger/test/t1")
        result = subprocess.run(
            ["git", "branch", "--list", "rigger/test/t1"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "rigger/test/t1" in result.stdout
        wt = git_repo.parent / ".rigger-worktrees" / "rigger" / "test" / "t1"
        manager.cleanup(wt)
        result = subprocess.run(
            ["git", "branch", "--list", "rigger/test/t1"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "rigger/test/t1" not in result.stdout

    def test_cleanup_idempotent(
        self, git_repo: Path, manager: GitWorktreeManager, task: Task
    ):
        wt = manager.create(git_repo, task, "rigger/test/t1")
        manager.cleanup(wt)
        # Second cleanup should not raise.
        manager.cleanup(wt)


class TestFullLifecycle:
    def test_create_modify_merge_cleanup(
        self, git_repo: Path, manager: GitWorktreeManager, task: Task
    ):
        # Create.
        wt = manager.create(git_repo, task, "rigger/test/lifecycle")
        assert wt.exists()

        # Modify.
        (wt / "output.txt").write_text("result\n")
        subprocess.run(["git", "add", "."], cwd=wt, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add output"],
            cwd=wt,
            check=True,
            capture_output=True,
        )

        # Merge.
        result = manager.merge(wt, git_repo)
        assert result.success is True
        assert (git_repo / "output.txt").read_text() == "result\n"

        # Cleanup.
        manager.cleanup(wt)
        assert not wt.exists()

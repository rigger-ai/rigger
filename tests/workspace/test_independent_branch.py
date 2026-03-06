"""Tests for IndependentBranchManager — branch-per-task with push."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rigger._types import MergeResult, Task
from rigger.workspace.independent_branch import IndependentBranchManager


@pytest.fixture
def bare_remote(tmp_path: Path) -> Path:
    """Create a bare git repository to serve as remote."""
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        capture_output=True,
    )
    return remote


@pytest.fixture
def git_repo(tmp_path: Path, bare_remote: Path) -> Path:
    """Create a git repository with a remote."""
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
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare_remote)],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "-u", "origin", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


@pytest.fixture
def manager() -> IndependentBranchManager:
    return IndependentBranchManager(create_pr=False)


@pytest.fixture
def task() -> Task:
    return Task(id="t1", description="Test task")


class TestCreate:
    def test_creates_worktree_directory(
        self, git_repo: Path, manager: IndependentBranchManager, task: Task
    ):
        wt = manager.create(git_repo, task, "rigger/test/t1")
        assert wt.exists()
        assert wt.is_dir()
        assert (wt / ".git").exists()

    def test_returns_path_under_rigger_worktrees(
        self, git_repo: Path, manager: IndependentBranchManager, task: Task
    ):
        wt = manager.create(git_repo, task, "rigger/test/t1")
        assert ".rigger-worktrees" in str(wt)

    def test_worktree_has_repo_files(
        self, git_repo: Path, manager: IndependentBranchManager, task: Task
    ):
        wt = manager.create(git_repo, task, "rigger/test/t1")
        assert (wt / "README.md").exists()
        assert (wt / "README.md").read_text() == "# Test\n"

    def test_worktree_is_on_correct_branch(
        self, git_repo: Path, manager: IndependentBranchManager, task: Task
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
        self, git_repo: Path, manager: IndependentBranchManager, task: Task
    ):
        wt1 = manager.create(git_repo, task, "rigger/test/t1")
        assert wt1.exists()
        wt2 = manager.create(git_repo, task, "rigger/test/t1")
        assert wt2.exists()
        assert wt1 == wt2

    def test_empty_repo_raises(self, tmp_path: Path, manager: IndependentBranchManager):
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        t = Task(id="t1", description="Test")
        with pytest.raises(RuntimeError, match="no commits"):
            manager.create(repo, t, "rigger/test/t1")


class TestMerge:
    def test_push_success(
        self,
        git_repo: Path,
        bare_remote: Path,
        manager: IndependentBranchManager,
        task: Task,
    ):
        wt = manager.create(git_repo, task, "rigger/test/t1")
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

        # Verify branch exists on remote.
        remote_branches = subprocess.run(
            ["git", "branch", "-r"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "origin/rigger/test/t1" in remote_branches.stdout

    def test_does_not_merge_locally(
        self,
        git_repo: Path,
        bare_remote: Path,
        manager: IndependentBranchManager,
        task: Task,
    ):
        wt = manager.create(git_repo, task, "rigger/test/t1")
        (wt / "new_file.txt").write_text("hello\n")
        subprocess.run(["git", "add", "."], cwd=wt, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add file"],
            cwd=wt,
            check=True,
            capture_output=True,
        )
        manager.merge(wt, git_repo)
        # File should NOT exist in main repo (no local merge).
        assert not (git_repo / "new_file.txt").exists()

    def test_push_failure_returns_failure(
        self, git_repo: Path, bare_remote: Path, task: Task
    ):
        mgr = IndependentBranchManager(remote="nonexistent", create_pr=False)
        wt = mgr.create(git_repo, task, "rigger/test/t1")
        (wt / "new_file.txt").write_text("hello\n")
        subprocess.run(["git", "add", "."], cwd=wt, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add file"],
            cwd=wt,
            check=True,
            capture_output=True,
        )
        result = mgr.merge(wt, git_repo)
        assert result.success is False
        assert result.worktree_path == wt
        assert "stderr" in result.metadata

    def test_push_no_changes_succeeds(
        self,
        git_repo: Path,
        bare_remote: Path,
        manager: IndependentBranchManager,
        task: Task,
    ):
        wt = manager.create(git_repo, task, "rigger/test/t1")
        # Make an empty commit so the branch has something to push.
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
        self, git_repo: Path, manager: IndependentBranchManager, task: Task
    ):
        wt = manager.create(git_repo, task, "rigger/test/t1")
        assert wt.exists()
        manager.cleanup(wt)
        assert not wt.exists()

    def test_cleanup_preserves_branch_by_default(
        self, git_repo: Path, manager: IndependentBranchManager, task: Task
    ):
        manager.create(git_repo, task, "rigger/test/t1")
        wt = git_repo.parent / ".rigger-worktrees" / "rigger" / "test" / "t1"
        manager.cleanup(wt)
        # Branch should still exist since cleanup_branch=False (default).
        result = subprocess.run(
            ["git", "branch", "--list", "rigger/test/t1"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "rigger/test/t1" in result.stdout

    def test_cleanup_deletes_branch_when_configured(
        self, git_repo: Path, bare_remote: Path, task: Task
    ):
        mgr = IndependentBranchManager(create_pr=False, cleanup_branch=True)
        mgr.create(git_repo, task, "rigger/test/t1")
        wt = git_repo.parent / ".rigger-worktrees" / "rigger" / "test" / "t1"
        mgr.cleanup(wt)
        result = subprocess.run(
            ["git", "branch", "--list", "rigger/test/t1"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "rigger/test/t1" not in result.stdout

    def test_cleanup_idempotent(
        self, git_repo: Path, manager: IndependentBranchManager, task: Task
    ):
        wt = manager.create(git_repo, task, "rigger/test/t1")
        manager.cleanup(wt)
        # Second cleanup should not raise.
        manager.cleanup(wt)


class TestFullLifecycle:
    def test_create_modify_push_cleanup(
        self,
        git_repo: Path,
        bare_remote: Path,
        manager: IndependentBranchManager,
        task: Task,
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

        # Push (merge).
        result = manager.merge(wt, git_repo)
        assert result.success is True
        # NOT in main repo (no local merge).
        assert not (git_repo / "output.txt").exists()

        # Cleanup.
        manager.cleanup(wt)
        assert not wt.exists()


class TestConstructorOptions:
    def test_custom_remote(self, git_repo: Path, bare_remote: Path, task: Task):
        # Add the bare repo as a differently-named remote.
        subprocess.run(
            ["git", "remote", "add", "upstream", str(bare_remote)],
            cwd=git_repo,
            check=True,
            capture_output=True,
        )
        mgr = IndependentBranchManager(remote="upstream", create_pr=False)
        wt = mgr.create(git_repo, task, "rigger/test/t1")
        (wt / "file.txt").write_text("data\n")
        subprocess.run(["git", "add", "."], cwd=wt, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "commit"],
            cwd=wt,
            check=True,
            capture_output=True,
        )
        result = mgr.merge(wt, git_repo)
        assert result.success is True

"""Tests for BranchPolicyConstraint."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rigger._types import VerifyAction
from rigger.constraints.branch_policy import BranchPolicyConstraint


def _init_repo(tmp_path: Path, branch: str) -> Path:
    """Create a minimal git repo on the given branch."""
    subprocess.run(
        ["git", "init", "-b", branch], cwd=tmp_path, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@rigger.dev"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Rigger Test"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    return tmp_path


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo on a feature branch."""
    return _init_repo(tmp_path, "feature/test")


@pytest.fixture
def main_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo on main branch."""
    return _init_repo(tmp_path, "main")


class TestProtectedBranch:
    def test_blocks_main(self, main_repo: Path):
        c = BranchPolicyConstraint()
        result = c.check(main_repo)
        assert result.passed is False
        assert result.action == VerifyAction.BLOCK
        assert "main" in result.message

    def test_blocks_custom_protected(self, tmp_path: Path):
        _init_repo(tmp_path, "release")
        c = BranchPolicyConstraint(protected_branches=["release", "main"])
        result = c.check(tmp_path)
        assert result.passed is False
        assert result.action == VerifyAction.BLOCK

    def test_allows_feature_branch(self, git_repo: Path):
        c = BranchPolicyConstraint()
        result = c.check(git_repo)
        assert result.passed is True
        assert result.action == VerifyAction.ACCEPT


class TestRequiredPrefix:
    def test_accepts_matching_prefix(self, git_repo: Path):
        c = BranchPolicyConstraint(required_prefix="feature/")
        result = c.check(git_repo)
        assert result.passed is True

    def test_blocks_wrong_prefix(self, git_repo: Path):
        c = BranchPolicyConstraint(required_prefix="task/")
        result = c.check(git_repo)
        assert result.passed is False
        assert result.action == VerifyAction.BLOCK
        assert "task/" in result.message

    def test_protected_takes_precedence_over_prefix(self, main_repo: Path):
        c = BranchPolicyConstraint(required_prefix="feature/")
        result = c.check(main_repo)
        assert result.passed is False
        assert "protected" in result.message.lower()


class TestNotAGitRepo:
    def test_blocks_non_git_directory(self, tmp_path: Path):
        c = BranchPolicyConstraint()
        result = c.check(tmp_path)
        assert result.passed is False
        assert result.action == VerifyAction.BLOCK
        assert "could not determine" in result.message.lower()


class TestBranchDetails:
    def test_branch_in_details_on_pass(self, git_repo: Path):
        c = BranchPolicyConstraint()
        result = c.check(git_repo)
        assert result.details["branch"] == "feature/test"

    def test_branch_in_details_on_block(self, main_repo: Path):
        c = BranchPolicyConstraint()
        result = c.check(main_repo)
        assert result.details["branch"] == "main"


class TestProtocolConformance:
    def test_satisfies_constraint_protocol(self):
        from rigger._protocols import Constraint

        c: Constraint = BranchPolicyConstraint()
        assert hasattr(c, "check")

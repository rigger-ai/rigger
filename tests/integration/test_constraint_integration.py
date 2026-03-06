"""Integration tests for Constraint implementations against real git repos."""

from __future__ import annotations

import json
import subprocess

from rigger._merge import merge_metadata
from rigger._schema import write_constraints
from rigger._types import VerifyAction
from rigger.constraints import BranchPolicyConstraint, ToolAllowlistConstraint


def test_branch_policy_blocks_main(git_project):
    constraint = BranchPolicyConstraint(protected_branches=["main", "master"])
    result = constraint.check(git_project)

    assert not result.passed
    assert result.action == VerifyAction.BLOCK


def test_branch_policy_allows_feature(git_project):
    subprocess.run(
        ["git", "checkout", "-b", "feature/test"],
        cwd=git_project,
        capture_output=True,
        check=True,
    )
    constraint = BranchPolicyConstraint(protected_branches=["main", "master"])
    result = constraint.check(git_project)

    assert result.passed


def test_tool_allowlist_metadata_roundtrip(git_project):
    constraint = ToolAllowlistConstraint(allowed=["Bash", "Read", "Edit"])
    result = constraint.check(git_project)

    assert result.passed
    assert result.metadata == {"allowed_tools": ["Bash", "Read", "Edit"]}

    merged = merge_metadata([result])
    write_constraints(git_project, merged)

    constraints_path = git_project / ".harness" / "constraints.json"
    data = json.loads(constraints_path.read_text())
    assert data["allowed_tools"] == ["Bash", "Edit", "Read"]

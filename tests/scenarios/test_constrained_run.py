"""Scenario tests: Constrained workflow (Composio C14 pattern).

Full multi-epoch runs with constraints (tool allowlist, branch policy).
"""

from __future__ import annotations

import os
import subprocess

from rigger._harness import Harness
from rigger._schema import read_constraints
from rigger.constraints import BranchPolicyConstraint, ToolAllowlistConstraint
from rigger.state_stores import HarnessDirStateStore
from rigger.task_sources import FileListTaskSource
from tests.helpers import DeterministicBackend, FileAction


def test_constrained_feature_branch(git_project, task_file):
    """Tasks complete on a feature branch with tool + branch constraints."""
    subprocess.run(
        ["git", "checkout", "-b", "feature/test"],
        cwd=git_project,
        capture_output=True,
        check=True,
    )

    backend = DeterministicBackend(
        actions={
            "t1": [FileAction(path="src/a.py", content="# a\n")],
            "t2": [FileAction(path="src/b.py", content="# b\n")],
        }
    )

    harness = Harness(
        project_root=git_project,
        backend=backend,
        task_source=FileListTaskSource(path="tasks.json"),
        constraints=[
            ToolAllowlistConstraint(allowed=["Bash", "Read", "Edit"]),
            BranchPolicyConstraint(protected_branches=["main", "master"]),
        ],
        state_store=HarnessDirStateStore(),
    )

    prev = os.getcwd()
    try:
        os.chdir(git_project)
        state = harness.run_sync(max_epochs=5, force_lock=True)
    finally:
        os.chdir(prev)

    assert len(state.completed_tasks) >= 2

    constraints = read_constraints(git_project)
    assert "allowed_tools" in constraints


def test_main_branch_blocked(git_project, task_file):
    """BranchPolicyConstraint blocks all epochs on protected main branch."""
    backend = DeterministicBackend(
        actions={
            "t1": [FileAction(path="src/a.py", content="# a\n")],
        }
    )

    harness = Harness(
        project_root=git_project,
        backend=backend,
        task_source=FileListTaskSource(path="tasks.json"),
        constraints=[
            BranchPolicyConstraint(protected_branches=["main", "master"]),
        ],
        state_store=HarnessDirStateStore(),
    )

    prev = os.getcwd()
    try:
        os.chdir(git_project)
        state = harness.run_sync(max_epochs=3, force_lock=True)
    finally:
        os.chdir(prev)

    assert len(state.completed_tasks) == 0
    # Pre-dispatch constraint failure causes `continue` (not halt)
    assert not state.halted

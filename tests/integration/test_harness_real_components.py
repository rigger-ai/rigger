"""Integration tests wiring real components through the Harness — B6."""

import os

from rigger._harness import Harness
from rigger.constraints import BranchPolicyConstraint
from rigger.context_sources import FileTreeContextSource
from rigger.state_stores import HarnessDirStateStore
from rigger.task_sources import FileListTaskSource
from rigger.verifiers import TestSuiteVerifier
from tests.helpers import DeterministicBackend, FileAction


def test_single_epoch_real_components(git_project, task_file):
    src_dir = git_project / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("# main\n")

    backend = DeterministicBackend(
        actions={"t1": [FileAction(path="src/feature_1.py", content="# feature 1\n")]}
    )
    task_source = FileListTaskSource(path="tasks.json")
    context_sources = [FileTreeContextSource(root="src")]
    state_store = HarnessDirStateStore()
    harness = Harness(
        project_root=git_project,
        backend=backend,
        task_source=task_source,
        context_sources=context_sources,
        state_store=state_store,
    )

    original_cwd = os.getcwd()
    try:
        os.chdir(git_project)
        state = harness.run_sync(max_epochs=1, force_lock=True)
    finally:
        os.chdir(original_cwd)

    assert "t1" in state.completed_tasks
    assert (git_project / "src" / "feature_1.py").exists()

    loaded = state_store.load(git_project)
    assert loaded.epoch >= 1


def test_verify_action_retry(git_project, task_file):
    # Verifier script: fails first time (n=0), succeeds on second (n>=1)
    verifier = TestSuiteVerifier(
        command=[
            "bash",
            "-c",
            "f=.harness/attempt; n=$(cat $f 2>/dev/null || echo 0); "
            "echo $((n+1)) > $f; [ $n -ge 1 ]",
        ]
    )
    backend = DeterministicBackend(
        actions={"t1": [FileAction(path="src/feature.py", content="# done")]}
    )
    state_store = HarnessDirStateStore()
    harness = Harness(
        project_root=git_project,
        backend=backend,
        task_source=FileListTaskSource(path="tasks.json"),
        verifiers=[verifier],
        state_store=state_store,
    )

    original_cwd = os.getcwd()
    try:
        os.chdir(git_project)
        state = harness.run_sync(max_epochs=3, max_retries=3, force_lock=True)
    finally:
        os.chdir(original_cwd)

    assert "t1" in state.completed_tasks
    assert backend.call_counts["t1"] >= 2


def test_constraint_blocks_dispatch(git_project, task_file):
    constraint = BranchPolicyConstraint(protected_branches=["main", "master"])
    backend = DeterministicBackend()
    state_store = HarnessDirStateStore()
    harness = Harness(
        project_root=git_project,
        backend=backend,
        task_source=FileListTaskSource(path="tasks.json"),
        constraints=[constraint],
        state_store=state_store,
    )

    original_cwd = os.getcwd()
    try:
        os.chdir(git_project)
        state = harness.run_sync(max_epochs=3, force_lock=True)
    finally:
        os.chdir(original_cwd)

    assert len(state.completed_tasks) == 0

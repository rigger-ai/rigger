"""Scenario tests: Feature-driven workflow (Anthropic C1/C3 pattern).

Full multi-epoch runs with DeterministicBackend, verifiers, and state stores.
"""

from __future__ import annotations

import json
import os

from rigger._harness import Harness
from rigger.context_sources import FileTreeContextSource
from rigger.state_stores import HarnessDirStateStore
from rigger.task_sources import FileListTaskSource
from rigger.verifiers import TestSuiteVerifier
from tests.helpers import DeterministicBackend, FileAction


def test_three_feature_run(git_project, task_file):
    """Three tasks complete across epochs with FileListTaskSource."""
    (git_project / "src").mkdir()
    (git_project / "src" / "starter.py").write_text("# starter\n")

    backend = DeterministicBackend(
        actions={
            "t1": [FileAction(path="src/feature_1.py", content="# feature 1\n")],
            "t2": [FileAction(path="src/feature_2.py", content="# feature 2\n")],
            "t3": [FileAction(path="src/feature_3.py", content="# feature 3\n")],
        }
    )

    harness = Harness(
        project_root=git_project,
        backend=backend,
        task_source=FileListTaskSource(path="tasks.json"),
        context_sources=[FileTreeContextSource(root="src")],
        verifiers=[TestSuiteVerifier(command=["bash", "-c", "exit 0"])],
        state_store=HarnessDirStateStore(),
    )

    prev = os.getcwd()
    try:
        os.chdir(git_project)
        state = harness.run_sync(max_epochs=5, force_lock=True)
    finally:
        os.chdir(prev)

    assert len(state.completed_tasks) == 3
    assert set(state.completed_tasks) == {"t1", "t2", "t3"}

    for n in [1, 2, 3]:
        assert (git_project / f"src/feature_{n}.py").exists()

    tasks = json.loads((git_project / "tasks.json").read_text())
    assert all(t["status"] == "done" for t in tasks)

    assert state.epoch >= 3


def test_verification_failure_retries(git_project, task_file):
    """A failing verifier triggers retries; task completes on second attempt."""
    backend = DeterministicBackend(
        actions={
            "t1": [FileAction(path="src/feature_1.py", content="# feature 1\n")],
        }
    )

    # Script tracks attempts via a file. Fails when n=0, passes when n>=1.
    verify_cmd = [
        "bash",
        "-c",
        "f=.harness/attempt; n=$(cat $f 2>/dev/null || echo 0); "
        "echo $((n+1)) > $f; [ $n -ge 1 ]",
    ]

    harness = Harness(
        project_root=git_project,
        backend=backend,
        task_source=FileListTaskSource(path="tasks.json"),
        verifiers=[TestSuiteVerifier(command=verify_cmd)],
        state_store=HarnessDirStateStore(),
    )

    prev = os.getcwd()
    try:
        os.chdir(git_project)
        state = harness.run_sync(max_epochs=5, max_retries=3, force_lock=True)
    finally:
        os.chdir(prev)

    assert "t1" in state.completed_tasks
    assert backend.call_counts["t1"] >= 2

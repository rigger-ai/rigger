"""Scenario tests: Plan-driven workflow (OpenAI C2/C5 pattern).

Full multi-epoch runs with JsonStoriesTaskSource, entropy detection,
and JSON file state persistence.
"""

from __future__ import annotations

import json
import os
import time

from rigger._harness import Harness
from rigger.context_sources import StaticFilesContextSource
from rigger.entropy_detectors import DocStalenessEntropyDetector
from rigger.state_stores import JsonFileStateStore
from rigger.task_sources import JsonStoriesTaskSource
from rigger.verifiers import LintVerifier
from tests.helpers import DeterministicBackend, FileAction


def test_stories_with_entropy(git_project, stories_file):
    """Three stories complete; stale docs trigger entropy tasks."""
    docs_dir = git_project / "docs"
    docs_dir.mkdir()
    plan_path = docs_dir / "plan.md"
    plan_path.write_text("# Project Plan\n\nBuild the features.\n")

    # Set mtime to 60 days ago so staleness detector fires
    old_time = time.time() - (60 * 86400)
    os.utime(plan_path, (old_time, old_time))

    backend = DeterministicBackend(
        actions={
            "s1": [FileAction(path="src/signup.py", content="# signup\n")],
            "s2": [FileAction(path="src/login.py", content="# login\n")],
            "s3": [FileAction(path="src/reset.py", content="# reset\n")],
        }
    )

    harness = Harness(
        project_root=git_project,
        backend=backend,
        task_source=JsonStoriesTaskSource(path="stories.json"),
        context_sources=[
            StaticFilesContextSource(
                source="docs/plan.md", destination="context/plan.md"
            ),
        ],
        verifiers=[LintVerifier(command=["bash", "-c", "exit 0"])],
        entropy_detectors=[
            DocStalenessEntropyDetector(patterns=["docs/**/*.md"], max_age_days=0),
        ],
        state_store=JsonFileStateStore(path="state.json"),
    )

    prev = os.getcwd()
    try:
        os.chdir(git_project)
        state = harness.run_sync(max_epochs=6, force_lock=True)
    finally:
        os.chdir(prev)

    assert len(state.completed_tasks) == 3
    assert set(state.completed_tasks) == {"s1", "s2", "s3"}

    data = json.loads((git_project / "stories.json").read_text())
    assert all(s["status"] == "done" for s in data["stories"])

    state_data = json.loads((git_project / "state.json").read_text())
    assert state_data["epoch"] >= 3

"""Declarative tests — YAML config to running harness."""

from __future__ import annotations

import os

import yaml
from click.testing import CliRunner

from rigger._config import build_harness, load_config
from rigger.cli import main
from tests.helpers import DeterministicBackend, FileAction


def test_yaml_feature_driven_e2e(git_project, task_file):
    yaml_path = git_project / "harness.yaml"
    yaml_path.write_text(
        yaml.dump(
            {
                "backend": {"type": "claude_code"},
                "task_source": {"type": "file_list", "path": "tasks.json"},
            }
        )
    )

    config = load_config(yaml_path)
    harness = build_harness(config, project_root=git_project)

    harness.backend = DeterministicBackend(
        actions={
            "t1": [FileAction(path="src/f1.py", content="# f1")],
            "t2": [FileAction(path="src/f2.py", content="# f2")],
            "t3": [FileAction(path="src/f3.py", content="# f3")],
        }
    )

    original = os.getcwd()
    try:
        os.chdir(git_project)
        state = harness.run_sync(max_epochs=5, force_lock=True)
    finally:
        os.chdir(original)

    assert len(state.completed_tasks) == 3


def test_cli_dry_run_real_config(git_project, task_file):
    yaml_path = git_project / "harness.yaml"
    yaml_path.write_text(
        yaml.dump(
            {
                "backend": {"type": "claude_code"},
                "task_source": {"type": "file_list", "path": "tasks.json"},
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(yaml_path), "--dry-run"])

    assert result.exit_code == 0
    assert "Config is valid" in result.output

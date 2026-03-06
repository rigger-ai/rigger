"""Declarative tests — YAML config to real Harness instances."""

from __future__ import annotations

import json

import yaml

from rigger._config import build_harness, load_config
from rigger._harness import Harness
from rigger.backends.claude_code import ClaudeCodeBackend
from rigger.constraints import BranchPolicyConstraint, ToolAllowlistConstraint
from rigger.entropy_detectors import DocStalenessEntropyDetector
from rigger.state_stores import HarnessDirStateStore
from rigger.task_sources import FileListTaskSource
from rigger.verifiers import TestSuiteVerifier


def test_minimal_yaml_builds_real_harness(git_project, task_file):
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

    assert isinstance(harness, Harness)
    assert isinstance(harness.task_source, FileListTaskSource)
    assert isinstance(harness.backend, ClaudeCodeBackend)


def test_full_yaml_all_sections(git_project, task_file):
    (git_project / "src").mkdir()

    yaml_path = git_project / "harness.yaml"
    yaml_path.write_text(
        yaml.dump(
            {
                "backend": {"type": "claude_code"},
                "task_source": {"type": "file_list", "path": "tasks.json"},
                "context_sources": [{"type": "file_tree", "root": "src"}],
                "verifiers": [
                    {"type": "test_suite", "command": ["echo", "ok"]},
                ],
                "constraints": [
                    {"type": "tool_allowlist", "allowed": ["Bash", "Read"]},
                    {"type": "branch_policy"},
                ],
                "state_store": {"type": "harness_dir"},
                "entropy_detectors": [
                    {"type": "doc_staleness", "patterns": ["docs/**/*.md"]},
                ],
            }
        )
    )

    config = load_config(yaml_path)
    harness = build_harness(config, project_root=git_project)

    assert isinstance(harness, Harness)
    assert isinstance(harness.task_source, FileListTaskSource)
    assert len(harness.verifiers) == 1
    assert isinstance(harness.verifiers[0], TestSuiteVerifier)
    assert len(harness.constraints) == 2
    assert isinstance(harness.constraints[0], ToolAllowlistConstraint)
    assert isinstance(harness.constraints[1], BranchPolicyConstraint)
    assert isinstance(harness.state_store, HarnessDirStateStore)
    assert len(harness.entropy_detectors) == 1
    assert isinstance(harness.entropy_detectors[0], DocStalenessEntropyDetector)


def test_yaml_path_resolution(git_project):
    config_dir = git_project / "config"
    config_dir.mkdir()

    tasks = [
        {"id": "t1", "description": "Task one", "status": "pending"},
        {"id": "t2", "description": "Task two", "status": "pending"},
        {"id": "t3", "description": "Task three", "status": "pending"},
    ]
    (config_dir / "tasks.json").write_text(json.dumps(tasks))

    yaml_path = config_dir / "harness.yaml"
    yaml_path.write_text(
        yaml.dump(
            {
                "backend": {"type": "claude_code"},
                "task_source": {"type": "file_list", "path": "tasks.json"},
            }
        )
    )

    config = load_config(yaml_path)
    harness = build_harness(config)

    # config_dir is the project_root when no explicit project_root is given
    tasks = harness.task_source.pending(config_dir)
    assert len(tasks) == 3

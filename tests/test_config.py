"""Tests for the YAML config loader."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from rigger._config import (
    RunConfig,
    build_harness,
    get_stop_predicate,
    load_config,
)

# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def minimal_yaml(tmp_path):
    """Write a minimal valid harness.yaml and return its path."""
    content = """\
backend:
  type: claude_code

task_source:
  type: file_list
  path: tasks.json
"""
    p = tmp_path / "harness.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def full_yaml(tmp_path):
    """Write a fully-specified harness.yaml and return its path."""
    content = """\
backend:
  type: claude_code
  model: claude-sonnet-4-6

task_source:
  type: file_list
  path: tasks.json

context_sources:
  - type: file_tree
    root: docs/

verifiers:
  - type: test_suite
    command:
      - pytest
    timeout: 120

constraints:
  - type: tool_allowlist
    allowed:
      - Bash
      - Read

state_store:
  type: harness_dir

entropy_detectors:
  - type: doc_staleness
    patterns:
      - "docs/**/*.md"
    max_age_days: 14

workspace:
  type: independent_branch

run:
  max_epochs: 10
  max_retries: 5
  stop_when: all_tasks_done
  inject_entropy_tasks: false
"""
    p = tmp_path / "harness.yaml"
    p.write_text(content)
    return p


# ── load_config ───────────────────────────────────────────────


class TestLoadConfig:
    def test_minimal_config(self, minimal_yaml):
        config = load_config(minimal_yaml)

        assert config.backend.type == "claude_code"
        assert config.backend.params == {}
        assert config.task_source.type == "file_list"
        assert config.task_source.params["path"] == "tasks.json"
        assert config.context_sources == []
        assert config.verifiers == []
        assert config.constraints == []
        assert config.state_store is None
        assert config.entropy_detectors == []
        assert config.workspace is None
        assert config.run == RunConfig()

    def test_full_config(self, full_yaml):
        config = load_config(full_yaml)

        assert config.backend.type == "claude_code"
        assert config.backend.params["model"] == "claude-sonnet-4-6"
        assert config.task_source.type == "file_list"
        assert len(config.context_sources) == 1
        assert config.context_sources[0].type == "file_tree"
        assert len(config.verifiers) == 1
        assert config.verifiers[0].type == "test_suite"
        assert config.verifiers[0].params["command"] == ["pytest"]
        assert len(config.constraints) == 1
        assert config.constraints[0].type == "tool_allowlist"
        assert config.state_store is not None
        assert config.state_store.type == "harness_dir"
        assert len(config.entropy_detectors) == 1
        assert config.entropy_detectors[0].type == "doc_staleness"
        assert config.workspace is not None
        assert config.workspace.type == "independent_branch"
        assert config.run.max_epochs == 10
        assert config.run.max_retries == 5
        assert config.run.stop_when == "all_tasks_done"
        assert config.run.inject_entropy_tasks is False

    def test_config_dir_set(self, minimal_yaml):
        config = load_config(minimal_yaml)
        assert config.config_dir == minimal_yaml.parent.resolve()

    def test_string_path_accepted(self, minimal_yaml):
        config = load_config(str(minimal_yaml))
        assert config.backend.type == "claude_code"


# ── Missing required fields ───────────────────────────────────


class TestMissingFields:
    def test_missing_backend(self, tmp_path):
        p = tmp_path / "harness.yaml"
        p.write_text("task_source:\n  type: file_list\n  path: tasks.json\n")

        with pytest.raises(ValueError, match="Missing required key: 'backend'"):
            load_config(p)

    def test_missing_task_source(self, tmp_path):
        p = tmp_path / "harness.yaml"
        p.write_text("backend:\n  type: claude_code\n")

        with pytest.raises(ValueError, match="Missing required key: 'task_source'"):
            load_config(p)

    def test_missing_type_in_component(self, tmp_path):
        p = tmp_path / "harness.yaml"
        p.write_text(
            "backend:\n  model: foo\ntask_source:\n  type: file_list\n  path: x\n"
        )

        with pytest.raises(ValueError, match="missing required key 'type'"):
            load_config(p)

    def test_file_not_found(self, tmp_path):
        p = tmp_path / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError, match="Config file not found"):
            load_config(p)

    def test_non_mapping_yaml(self, tmp_path):
        p = tmp_path / "harness.yaml"
        p.write_text("- just\n- a\n- list\n")

        with pytest.raises(ValueError, match="YAML mapping"):
            load_config(p)


# ── Environment variable interpolation ────────────────────────


class TestEnvVarInterpolation:
    def test_env_var_substitution(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_MODEL", "claude-opus-4-6")
        p = tmp_path / "harness.yaml"
        p.write_text(
            "backend:\n  type: claude_code\n  model: ${MY_MODEL}\n"
            "task_source:\n  type: file_list\n  path: tasks.json\n"
        )

        config = load_config(p)
        assert config.backend.params["model"] == "claude-opus-4-6"

    def test_env_var_with_default(self, tmp_path, monkeypatch):
        monkeypatch.delenv("UNSET_VAR", raising=False)
        p = tmp_path / "harness.yaml"
        p.write_text(
            "backend:\n  type: claude_code\n  model: ${UNSET_VAR:-fallback}\n"
            "task_source:\n  type: file_list\n  path: tasks.json\n"
        )

        config = load_config(p)
        assert config.backend.params["model"] == "fallback"

    def test_env_var_unset_no_default_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        p = tmp_path / "harness.yaml"
        p.write_text(
            "backend:\n  type: claude_code\n  model: ${MISSING_VAR}\n"
            "task_source:\n  type: file_list\n  path: tasks.json\n"
        )

        with pytest.raises(ValueError, match=r"MISSING_VAR.*not set"):
            load_config(p)

    def test_env_var_in_nested_list(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TOOL_NAME", "Bash")
        p = tmp_path / "harness.yaml"
        p.write_text(
            "backend:\n  type: claude_code\n"
            "task_source:\n  type: file_list\n  path: x\n"
            "constraints:\n  - type: tool_allowlist\n"
            "    allowed:\n      - ${TOOL_NAME}\n"
        )

        config = load_config(p)
        assert config.constraints[0].params["allowed"] == ["Bash"]


# ── Path resolution ──────────────────────────────────────────


class TestPathResolution:
    def test_relative_path_resolved_against_config_dir(self, tmp_path):
        subdir = tmp_path / "config"
        subdir.mkdir()
        p = subdir / "harness.yaml"
        p.write_text(
            "backend:\n  type: claude_code\n"
            "task_source:\n  type: file_list\n  path: tasks.json\n"
        )

        config = load_config(p)

        # Use a mock registry to intercept the create call
        mock_reg = MagicMock()
        mock_reg.create.return_value = MagicMock()

        with patch("rigger._config.registry", mock_reg):
            build_harness(config)

        # Find the task_source create call
        task_source_call = [
            c for c in mock_reg.create.call_args_list if c[0][0] == "task_source"
        ]
        assert len(task_source_call) == 1
        _, kwargs = task_source_call[0][0], task_source_call[0][1]
        # path should be resolved against config_dir
        assert kwargs["path"] == str(subdir.resolve() / "tasks.json")

    def test_absolute_path_not_modified(self, tmp_path):
        p = tmp_path / "harness.yaml"
        p.write_text(
            "backend:\n  type: claude_code\n"
            "task_source:\n  type: file_list\n  path: /absolute/tasks.json\n"
        )

        config = load_config(p)

        mock_reg = MagicMock()
        mock_reg.create.return_value = MagicMock()

        with patch("rigger._config.registry", mock_reg):
            build_harness(config)

        task_source_call = [
            c for c in mock_reg.create.call_args_list if c[0][0] == "task_source"
        ]
        assert task_source_call[0][1]["path"] == "/absolute/tasks.json"


# ── Unknown types ─────────────────────────────────────────────


class TestUnknownTypes:
    def test_unknown_backend_type(self, tmp_path):
        p = tmp_path / "harness.yaml"
        p.write_text(
            "backend:\n  type: nonexistent_backend\n"
            "task_source:\n  type: file_list\n  path: x\n"
        )

        config = load_config(p)

        with pytest.raises(
            KeyError, match="Unknown backend type 'nonexistent_backend'"
        ):
            build_harness(config)

    def test_unknown_task_source_type(self, tmp_path):
        p = tmp_path / "harness.yaml"
        p.write_text("backend:\n  type: claude_code\ntask_source:\n  type: bogus\n")

        config = load_config(p)

        with pytest.raises(KeyError, match="Unknown task_source type 'bogus'"):
            build_harness(config)

    def test_invalid_stop_when(self, tmp_path):
        p = tmp_path / "harness.yaml"
        p.write_text(
            "backend:\n  type: claude_code\n"
            "task_source:\n  type: file_list\n  path: x\n"
            "run:\n  stop_when: invalid_value\n"
        )

        with pytest.raises(ValueError, match="Invalid stop_when"):
            load_config(p)


# ── build_harness ─────────────────────────────────────────────


class TestBuildHarness:
    def test_build_minimal(self, minimal_yaml):
        config = load_config(minimal_yaml)

        mock_backend = MagicMock()
        mock_task_source = MagicMock()
        mock_reg = MagicMock()

        def create_side_effect(protocol, name, **kwargs):
            if protocol == "backend":
                return mock_backend
            if protocol == "task_source":
                return mock_task_source
            return MagicMock()

        mock_reg.create.side_effect = create_side_effect

        with patch("rigger._config.registry", mock_reg):
            harness = build_harness(config)

        assert harness.backend is mock_backend
        assert harness.task_source is mock_task_source
        assert harness.project_root == config.config_dir

    def test_build_with_explicit_project_root(self, minimal_yaml, tmp_path):
        config = load_config(minimal_yaml)
        custom_root = tmp_path / "my_project"
        custom_root.mkdir()

        mock_reg = MagicMock()
        mock_reg.create.return_value = MagicMock()

        with patch("rigger._config.registry", mock_reg):
            harness = build_harness(config, project_root=custom_root)

        assert harness.project_root == custom_root

    def test_build_passes_inject_entropy(self, tmp_path):
        p = tmp_path / "harness.yaml"
        p.write_text(
            "backend:\n  type: claude_code\n"
            "task_source:\n  type: file_list\n  path: x\n"
            "run:\n  inject_entropy_tasks: false\n"
        )
        config = load_config(p)

        mock_reg = MagicMock()
        mock_reg.create.return_value = MagicMock()

        with patch("rigger._config.registry", mock_reg):
            harness = build_harness(config)

        assert harness.inject_entropy_tasks is False

    def test_build_full_config(self, full_yaml):
        config = load_config(full_yaml)

        mock_reg = MagicMock()
        mock_reg.create.return_value = MagicMock()

        with patch("rigger._config.registry", mock_reg):
            build_harness(config)

        # Verify all protocol groups were created
        protocols_created = [call[0][0] for call in mock_reg.create.call_args_list]
        assert "backend" in protocols_created
        assert "task_source" in protocols_created
        assert "context_source" in protocols_created
        assert "verifier" in protocols_created
        assert "constraint" in protocols_created
        assert "state_store" in protocols_created
        assert "entropy_detector" in protocols_created
        assert "workspace_manager" in protocols_created


# ── get_stop_predicate ────────────────────────────────────────


class TestGetStopPredicate:
    def test_all_tasks_done(self):
        pred = get_stop_predicate("all_tasks_done")
        assert callable(pred)

    def test_max_epochs_never_stops(self):
        pred = get_stop_predicate("max_epochs")
        mock_state = MagicMock()
        assert pred(mock_state) is False

    def test_never_never_stops(self):
        pred = get_stop_predicate("never")
        mock_state = MagicMock()
        assert pred(mock_state) is False

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown stop_when"):
            get_stop_predicate("bogus")


# ── Unknown top-level keys ────────────────────────────────────


class TestWarnings:
    def test_unknown_top_level_key_warns(self, tmp_path, caplog):
        p = tmp_path / "harness.yaml"
        p.write_text(
            "backend:\n  type: claude_code\n"
            "task_source:\n  type: file_list\n  path: x\n"
            "extra_key: something\n"
        )

        import logging

        with caplog.at_level(logging.WARNING, logger="rigger._config"):
            load_config(p)

        assert "extra_key" in caplog.text

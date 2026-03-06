"""Tests for the rigger CLI."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from rigger.cli import (
    EXIT_CONFIG_ERROR,
    EXIT_HALTED,
    EXIT_LOCK_CONFLICT,
    EXIT_MAX_EPOCHS,
    EXIT_OK,
    _exit_code_for,
    main,
)

# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def minimal_yaml(tmp_path):
    content = """\
backend:
  type: claude_code

task_source:
  type: file_list
  path: tasks.txt
"""
    p = tmp_path / "harness.yaml"
    p.write_text(content)
    return p


# ── _exit_code_for tests ─────────────────────────────────────


def test_exit_code_ok():
    from rigger._types import EpochState

    state = EpochState(epoch=3, completed_tasks=["a", "b"], pending_tasks=[])
    assert _exit_code_for(state, max_epochs=10) == EXIT_OK


def test_exit_code_halted():
    from rigger._types import EpochState

    state = EpochState(halted=True, halt_reason="blocked")
    assert _exit_code_for(state, max_epochs=10) == EXIT_HALTED


def test_exit_code_max_epochs():
    from rigger._types import EpochState

    state = EpochState(epoch=10, pending_tasks=["c"])
    assert _exit_code_for(state, max_epochs=10) == EXIT_MAX_EPOCHS


# ── run command tests ────────────────────────────────────────


def test_run_config_not_found(runner, tmp_path):
    result = runner.invoke(main, ["--config", str(tmp_path / "nope.yaml"), "run"])
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert "Configuration error" in result.output


def test_run_invalid_yaml(runner, tmp_path):
    bad = tmp_path / "harness.yaml"
    bad.write_text("just a string\n")
    result = runner.invoke(main, ["--config", str(bad), "run"])
    assert result.exit_code == EXIT_CONFIG_ERROR


def test_run_dry_run(runner, minimal_yaml):
    result = runner.invoke(main, ["--config", str(minimal_yaml), "--dry-run", "run"])
    assert result.exit_code == EXIT_OK
    assert "Dry run" in result.output


def test_run_lock_conflict(runner, minimal_yaml):
    from rigger._lock import HarnessAlreadyRunning

    with patch("rigger._config.build_harness") as mock_bh:
        mock_harness = MagicMock()
        mock_harness.run_sync.side_effect = HarnessAlreadyRunning("locked")
        mock_bh.return_value = mock_harness
        result = runner.invoke(main, ["--config", str(minimal_yaml), "run"])
    assert result.exit_code == EXIT_LOCK_CONFLICT
    assert "Lock conflict" in result.output


def test_run_success(runner, minimal_yaml):
    from rigger._types import EpochState

    final_state = EpochState(epoch=3, completed_tasks=["a", "b"])

    with patch("rigger._config.build_harness") as mock_bh:
        mock_harness = MagicMock()
        mock_harness.run_sync.return_value = final_state
        mock_bh.return_value = mock_harness
        result = runner.invoke(main, ["--config", str(minimal_yaml), "run"])

    assert result.exit_code == EXIT_OK
    assert "Completed" in result.output


def test_run_halted(runner, minimal_yaml):
    from rigger._types import EpochState

    final_state = EpochState(halted=True, halt_reason="blocked")

    with patch("rigger._config.build_harness") as mock_bh:
        mock_harness = MagicMock()
        mock_harness.run_sync.return_value = final_state
        mock_bh.return_value = mock_harness
        result = runner.invoke(main, ["--config", str(minimal_yaml), "run"])

    assert result.exit_code == EXIT_HALTED
    assert "Halted" in result.output


# ── default command (no subcommand = run) ─────────────────────


def test_default_invokes_run(runner, minimal_yaml):
    from rigger._types import EpochState

    with patch("rigger._config.build_harness") as mock_bh:
        mock_harness = MagicMock()
        mock_harness.run_sync.return_value = EpochState(epoch=1, completed_tasks=["t"])
        mock_bh.return_value = mock_harness
        result = runner.invoke(main, ["--config", str(minimal_yaml)])

    assert result.exit_code == EXIT_OK
    assert "Completed" in result.output


# ── status command tests ─────────────────────────────────────


def test_status_no_harness_dir(runner, tmp_path):
    original = os.getcwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(main, ["status"])
    finally:
        os.chdir(original)
    assert result.exit_code == EXIT_OK
    assert "No .harness/" in result.output


def test_status_with_state(runner, tmp_path):
    harness_dir = tmp_path / ".harness"
    harness_dir.mkdir()
    state = {
        "_schema_version": "1.0",
        "epoch": 5,
        "completed_tasks": ["a", "b"],
        "pending_tasks": ["c"],
    }
    (harness_dir / "state.json").write_text(json.dumps(state))

    original = os.getcwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(main, ["status"])
    finally:
        os.chdir(original)

    assert result.exit_code == EXIT_OK
    assert "Epoch:     5" in result.output
    assert "Completed: 2" in result.output
    assert "Pending:   1" in result.output
    assert "67%" in result.output


# ── init command tests ───────────────────────────────────────


def test_init_creates_file(runner, tmp_path):
    output = tmp_path / "harness.yaml"
    result = runner.invoke(main, ["init", "-o", str(output)])
    assert result.exit_code == EXIT_OK
    assert output.exists()
    content = output.read_text()
    assert "backend:" in content
    assert "task_source:" in content


def test_init_confirm_overwrite(runner, tmp_path):
    output = tmp_path / "harness.yaml"
    output.write_text("existing")
    result = runner.invoke(main, ["init", "-o", str(output)], input="n\n")
    assert result.exit_code != EXIT_OK
    assert output.read_text() == "existing"


def test_init_overwrite_confirmed(runner, tmp_path):
    output = tmp_path / "harness.yaml"
    output.write_text("existing")
    result = runner.invoke(main, ["init", "-o", str(output)], input="y\n")
    assert result.exit_code == EXIT_OK
    assert "backend:" in output.read_text()


# ── --version flag ───────────────────────────────────────────


def test_version_flag(runner):
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == EXIT_OK
    assert "0.0.1" in result.output

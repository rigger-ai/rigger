"""Rigger CLI — declarative agent harness runner.

Provides the ``rigger`` command with subcommands ``run``, ``status``,
and ``init``.  The default (no subcommand) is equivalent to ``rigger run``.

Exit codes::

    0  All tasks completed successfully.
    1  Harness halted (BLOCK, ESCALATE, or max retries exhausted).
    2  Max epochs reached without completion.
    3  Configuration error (invalid YAML, unknown types, missing params).
    4  Lock conflict (another harness instance is running).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from rigger._types import EpochState

# ── Exit codes ────────────────────────────────────────────────

EXIT_OK = 0
EXIT_HALTED = 1
EXIT_MAX_EPOCHS = 2
EXIT_CONFIG_ERROR = 3
EXIT_LOCK_CONFLICT = 4


# ── Logging setup ────────────────────────────────────────────


def _configure_logging(verbose: bool) -> None:
    """Set up root logging for the CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


# ── Exit code helpers ────────────────────────────────────────


def _exit_code_for(state: EpochState, max_epochs: int) -> int:
    """Map final EpochState to an exit code."""
    if state.halted:
        return EXIT_HALTED
    if state.epoch >= max_epochs and state.pending_tasks:
        return EXIT_MAX_EPOCHS
    return EXIT_OK


# ── CLI group ────────────────────────────────────────────────


@click.group(invoke_without_command=True)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=False),
    default="harness.yaml",
    help="Path to harness.yaml config file.",
    show_default=True,
)
@click.option("--force", is_flag=True, help="Override existing lock file.")
@click.option("--verbose", "-v", is_flag=True, help="Increase log verbosity.")
@click.option(
    "--dry-run", is_flag=True, help="Parse and validate config without running."
)
@click.version_option(package_name="rigger")
@click.pass_context
def main(
    ctx: click.Context,
    config_path: str,
    force: bool,
    verbose: bool,
    dry_run: bool,
) -> None:
    """Rigger — declarative agent harness framework."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path
    ctx.obj["force"] = force
    ctx.obj["verbose"] = verbose
    ctx.obj["dry_run"] = dry_run

    # Default to "run" if no subcommand given
    if ctx.invoked_subcommand is None:
        ctx.invoke(run_cmd)


# ── run command ──────────────────────────────────────────────


@main.command("run")
@click.pass_context
def run_cmd(ctx: click.Context) -> None:
    """Run the harness loop (default command)."""
    opts = ctx.obj
    _configure_logging(opts["verbose"])

    from rigger._config import build_harness, get_stop_predicate, load_config
    from rigger._lock import HarnessAlreadyRunning

    config_file = Path(opts["config_path"])

    try:
        config = load_config(config_file)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        raise SystemExit(EXIT_CONFIG_ERROR) from None

    try:
        harness = build_harness(config)
    except (KeyError, TypeError) as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        raise SystemExit(EXIT_CONFIG_ERROR) from None

    if opts["dry_run"]:
        click.echo("Config is valid. Dry run — not executing.")
        return

    stop_when = get_stop_predicate(config.run.stop_when)

    try:
        state = harness.run_sync(
            max_epochs=config.run.max_epochs,
            max_retries=config.run.max_retries,
            stop_when=stop_when,
            force_lock=opts["force"],
        )
    except HarnessAlreadyRunning as exc:
        click.echo(f"Lock conflict: {exc}", err=True)
        raise SystemExit(EXIT_LOCK_CONFLICT) from None

    code = _exit_code_for(state, config.run.max_epochs)
    if code == EXIT_OK:
        click.echo(
            f"Completed — {len(state.completed_tasks)} tasks done "
            f"in {state.epoch} epochs."
        )
    elif code == EXIT_HALTED:
        click.echo(f"Halted — reason: {state.halt_reason}", err=True)
    else:
        click.echo(
            f"Max epochs ({config.run.max_epochs}) reached — "
            f"{len(state.pending_tasks)} tasks remaining.",
            err=True,
        )

    if code != EXIT_OK:
        raise SystemExit(code)


# ── status command ───────────────────────────────────────────


@main.command("status")
@click.pass_context
def status_cmd(ctx: click.Context) -> None:
    """Display current harness state from .harness/ directory."""
    _configure_logging(ctx.obj["verbose"])

    from rigger._lock import _read_lock
    from rigger._schema import HARNESS_DIR, read_current_task, read_state

    project_root = Path.cwd()
    harness_dir = project_root / HARNESS_DIR

    if not harness_dir.exists():
        click.echo("No .harness/ directory found in current directory.")
        return

    state = read_state(project_root)
    task = read_current_task(project_root)
    lock = _read_lock(project_root)

    click.echo(f"Epoch:     {state.epoch}")
    click.echo(f"Completed: {len(state.completed_tasks)} tasks")
    click.echo(f"Pending:   {len(state.pending_tasks)} tasks")

    if state.completed_tasks and state.pending_tasks:
        total = len(state.completed_tasks) + len(state.pending_tasks)
        pct = len(state.completed_tasks) / total * 100
        click.echo(f"Progress:  {pct:.0f}%")

    if state.halted:
        click.echo(f"Status:    HALTED ({state.halt_reason})")
    elif task:
        click.echo(f"Status:    RUNNING (task: {task.id})")
    else:
        click.echo("Status:    IDLE")

    if lock:
        import time

        click.echo(
            f"Lock:      pid={lock.pid} host={lock.hostname} "
            f"since {time.ctime(lock.timestamp)}"
        )


# ── init command ─────────────────────────────────────────────

_STARTER_YAML = """\
# Rigger harness configuration
# Docs: https://rigger-ai.github.io/rigger/

backend:
  type: claude_code
  # model: claude-sonnet-4-6
  # setting_sources:
  #   - project

task_source:
  type: file_list
  path: tasks.txt
  # Alternatives:
  #   type: json_stories
  #   path: stories.json
  #
  #   type: linear
  #   team_id: ${LINEAR_TEAM_ID}
  #   api_key: ${LINEAR_API_KEY}
  #
  #   type: atomic_issue
  #   owner: myorg
  #   repo: myrepo

# context_sources:
#   - type: file_tree
#     root: src/
#   - type: agents_md
#   - type: static_files
#     paths:
#       - docs/architecture.md
#   - type: mcp_capability

# verifiers:
#   - type: test_suite
#     command: pytest
#   - type: lint
#     command: ruff check .
#   - type: ci_status
#   - type: ratchet
#     metric: coverage
#     threshold: 80.0

# constraints:
#   - type: tool_allowlist
#     tools:
#       - Read
#       - Edit
#       - Bash
#   - type: branch_policy
#     pattern: "feature/*"

# state_store:
#   type: json_file
#   path: .harness/state.json

# entropy_detectors:
#   - type: shell_command
#     command: "git diff --stat HEAD~1"
#   - type: doc_staleness
#     paths:
#       - docs/

# workspace:
#   type: git_worktree
#   Alternatives:
#     type: independent_branch
#     type: independent_dir

# run:
#   max_epochs: 100
#   max_retries: 3
#   stop_when: all_tasks_done
#   inject_entropy_tasks: true
"""


@main.command("init")
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="harness.yaml",
    help="Output file path.",
    show_default=True,
)
@click.option(
    "--template",
    "-t",
    "template_name",
    default=None,
    help="Copy a built-in template instead of the starter YAML.",
)
@click.option(
    "--list-templates",
    is_flag=True,
    help="List available templates and exit.",
)
@click.pass_context
def init_cmd(
    ctx: click.Context,
    output: str,
    template_name: str | None,
    list_templates: bool,
) -> None:
    """Generate a starter harness.yaml or copy a built-in template."""
    _configure_logging(ctx.obj["verbose"])

    from rigger.templates import copy_template
    from rigger.templates import list_templates as _list_templates

    if list_templates:
        names = _list_templates()
        if not names:
            click.echo("No templates available.")
        else:
            click.echo("Available templates:")
            for name in names:
                click.echo(f"  {name}")
        return

    if template_name is not None:
        dest = Path.cwd()
        try:
            created = copy_template(template_name, dest)
        except KeyError as exc:
            click.echo(str(exc), err=True)
            raise SystemExit(EXIT_CONFIG_ERROR) from None

        for rel in created:
            click.echo(f"  {rel}")
        click.echo(
            f"Initialized from template '{template_name}'. "
            "Edit the files, then run: rigger"
        )
        return

    path = Path(output)
    if path.exists():
        click.confirm(f"{path} already exists. Overwrite?", abort=True)

    path.write_text(_STARTER_YAML)
    click.echo(f"Created {path}")
    click.echo("Edit the file to configure your harness, then run: rigger")

"""Test helpers — deterministic backend and utilities for integration tests."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from rigger._schema import read_current_task
from rigger._types import TaskResult


@dataclass
class FileAction:
    """A predetermined file change for DeterministicBackend."""

    path: str
    content: str = ""
    delete: bool = False


class DeterministicBackend:
    """AgentBackend that creates predetermined file changes + git commits.

    Maps task IDs to lists of file actions. When execute() is called,
    reads current_task.json to determine which task is active, applies
    the corresponding file changes, and creates a git commit.

    This is a real AgentBackend — it makes real filesystem and git
    changes, so verifiers, state stores, and constraints see real
    artifacts.
    """

    def __init__(
        self,
        actions: dict[str, list[FileAction]] | None = None,
        *,
        default_result_status: str = "success",
    ) -> None:
        self._actions: dict[str, list[FileAction]] = actions or {}
        self._default_status = default_result_status
        self._call_count: dict[str, int] = {}

    @property
    def call_counts(self) -> dict[str, int]:
        """How many times each task_id was dispatched."""
        return dict(self._call_count)

    async def execute(self, project_root: Path) -> TaskResult:
        """Apply predetermined file changes and commit."""
        task = read_current_task(project_root)
        task_id = task.id if task else "unknown"

        self._call_count[task_id] = self._call_count.get(task_id, 0) + 1

        file_actions = self._actions.get(task_id, [])
        for action in file_actions:
            target = project_root / action.path
            if action.delete:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(action.content, encoding="utf-8")

        # Stage and commit
        subprocess.run(
            ["git", "add", "."],
            cwd=project_root,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"Task {task_id}", "--allow-empty"],
            cwd=project_root,
            capture_output=True,
            check=True,
        )

        return TaskResult(task_id=task_id, status=self._default_status)


class RetryAwareDeterministicBackend(DeterministicBackend):
    """DeterministicBackend that produces different output on retry.

    On the first call for a task, applies `first_actions`. On subsequent
    calls, applies `retry_actions`.
    """

    def __init__(
        self,
        first_actions: dict[str, list[FileAction]],
        retry_actions: dict[str, list[FileAction]],
    ) -> None:
        super().__init__()
        self._first_actions = first_actions
        self._retry_actions = retry_actions

    async def execute(self, project_root: Path) -> TaskResult:
        """Apply first_actions on first call, retry_actions on subsequent calls."""
        task = read_current_task(project_root)
        task_id = task.id if task else "unknown"
        count = self._call_count.get(task_id, 0)

        if count == 0:
            self._actions = self._first_actions
        else:
            self._actions = self._retry_actions

        return await super().execute(project_root)

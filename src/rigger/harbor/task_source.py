"""InstructionTaskSource — wraps a single instruction string into a Rigger Task."""

from __future__ import annotations

from pathlib import Path

from rigger._types import Task, TaskResult


class InstructionTaskSource:
    """TaskSource that yields a single task from a Harbor instruction string.

    Once ``mark_complete()`` is called, ``pending()`` returns an empty list.
    """

    def __init__(self, instruction: str, *, task_id: str = "swebench") -> None:
        self._task = Task(id=task_id, description=instruction)
        self._done = False

    def pending(self, project_root: Path) -> list[Task]:
        """Return the single task until marked done."""
        if self._done:
            return []
        return [self._task]

    def mark_complete(self, task_id: str, result: TaskResult | None = None) -> None:
        """Mark the task as done so subsequent ``pending()`` returns ``[]``."""
        if task_id == self._task.id:
            self._done = True

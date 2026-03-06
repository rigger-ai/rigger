"""FileListTaskSource — reads a JSON file containing an array of task objects.

Config name: ``file_list``

Corpus pattern TD-1: Feature backlog with immutable schema.
Sources: C1 (Anthropic), C2 (OpenAI), C3 (Anthropic Quickstart).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path

from rigger._types import Task, TaskResult

logger = logging.getLogger(__name__)


class FileListTaskSource:
    """Reads a JSON file with task objects; marks complete by updating status.

    The JSON file must contain an array of objects, each with at least
    ``id`` and ``description`` fields. An optional ``status`` field tracks
    completion (defaults to ``"pending"``).

    Example JSON::

        [
            {"id": "t1", "description": "Add login page", "status": "pending"},
            {"id": "t2", "description": "Add tests", "status": "done"}
        ]

    Args:
        path: Path to the JSON file (relative to project_root or absolute).
    """

    def __init__(self, path: str) -> None:  # noqa: D107
        self._path = path

    def pending(self, project_root: Path) -> list[Task]:
        """Return tasks with status != ``"done"``, in array order."""
        file_path = self._resolve(project_root)
        if not file_path.exists():
            return []

        try:
            items = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read task file %s: %s", file_path, exc)
            return []

        if not isinstance(items, list):
            logger.warning("Task file %s does not contain a JSON array", file_path)
            return []

        tasks: list[Task] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("status", "pending") == "done":
                continue
            task_id = item.get("id", "")
            if not task_id:
                continue
            tasks.append(
                Task(
                    id=str(task_id),
                    description=item.get("description", ""),
                    metadata={
                        k: v
                        for k, v in item.items()
                        if k not in ("id", "description", "status")
                    },
                )
            )
        return tasks

    def mark_complete(self, task_id: str, result: TaskResult) -> None:
        """Update the task's status to ``"done"`` in the JSON file.

        Uses atomic write (write to temp file, then rename) to avoid
        partial writes on crash.
        """
        file_path = self._resolve_for_write()
        if not file_path.exists():
            logger.warning("Task file %s not found for mark_complete", file_path)
            return

        try:
            items = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read task file %s: %s", file_path, exc)
            return

        if not isinstance(items, list):
            return

        for item in items:
            if isinstance(item, dict) and str(item.get("id", "")) == task_id:
                item["status"] = "done"
                break

        self._atomic_write(file_path, items)

    def _resolve(self, project_root: Path) -> Path:
        p = Path(self._path)
        if p.is_absolute():
            return p
        return project_root / p

    def _resolve_for_write(self) -> Path:
        """Resolve path for write operations.

        mark_complete doesn't receive project_root, so the path must be
        absolute or we fall back to CWD. In normal harness usage, the path
        is resolved during pending() and tasks are marked complete in the
        same working directory.
        """
        p = Path(self._path)
        if p.is_absolute():
            return p
        return Path.cwd() / p

    @staticmethod
    def _atomic_write(file_path: Path, data: list[dict[str, object]]) -> None:
        """Write JSON data atomically via temp file + rename."""
        content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        fd, tmp_path = tempfile.mkstemp(
            dir=file_path.parent, suffix=".tmp", prefix=".task_"
        )
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            os.replace(tmp_path, file_path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.close(fd)
            Path(tmp_path).unlink(missing_ok=True)
            raise

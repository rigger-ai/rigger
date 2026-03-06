"""JsonStoriesTaskSource — reads a PRD-style JSON file with stories/features.

Config name: ``json_stories``

Corpus pattern TD-7: Iterative task loop with context reset.
Source: C9 (Osmani "Self-Improving Coding Agents").
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


class JsonStoriesTaskSource:
    """Reads a PRD-style JSON file with stories, one per cycle.

    The JSON file must contain an object with a key (default ``"stories"``)
    that maps to an array of story objects. Each story needs at least
    ``id`` and ``description`` fields. An optional ``status`` field
    tracks completion (defaults to ``"pending"``).

    Example JSON::

        {
            "stories": [
                {"id": "s1", "description": "User can sign up", "status": "pending"},
                {"id": "s2", "description": "User can log in"}
            ]
        }

    Args:
        path: Path to the JSON file (relative to project_root or absolute).
        key: JSON key containing the stories array.
    """

    def __init__(self, path: str, key: str = "stories") -> None:  # noqa: D107
        self._path = path
        self._key = key

    def pending(self, project_root: Path) -> list[Task]:
        """Return incomplete stories in order, one per cycle."""
        file_path = self._resolve(project_root)
        if not file_path.exists():
            return []

        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read stories file %s: %s", file_path, exc)
            return []

        if not isinstance(data, dict):
            logger.warning("Stories file %s does not contain a JSON object", file_path)
            return []

        stories = data.get(self._key, [])
        if not isinstance(stories, list):
            logger.warning(
                "Key %r in %s does not contain an array", self._key, file_path
            )
            return []

        for story in stories:
            if not isinstance(story, dict):
                continue
            status = story.get("status", "pending")
            if status == "done":
                continue
            story_id = story.get("id", "")
            if not story_id:
                continue
            # One per cycle
            return [
                Task(
                    id=str(story_id),
                    description=story.get("description", story.get("story", "")),
                    metadata={
                        k: v
                        for k, v in story.items()
                        if k not in ("id", "description", "story", "status")
                    },
                )
            ]

        return []

    def mark_complete(self, task_id: str, result: TaskResult) -> None:
        """Mark the story as completed in the JSON file.

        Uses atomic write (write to temp file, then rename).
        """
        file_path = self._resolve_for_write()
        if not file_path.exists():
            logger.warning("Stories file %s not found for mark_complete", file_path)
            return

        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read stories file %s: %s", file_path, exc)
            return

        if not isinstance(data, dict):
            return

        stories = data.get(self._key, [])
        if not isinstance(stories, list):
            return

        for story in stories:
            if isinstance(story, dict) and str(story.get("id", "")) == task_id:
                story["status"] = "done"
                break

        self._atomic_write(file_path, data)

    def _resolve(self, project_root: Path) -> Path:
        p = Path(self._path)
        if p.is_absolute():
            return p
        return project_root / p

    def _resolve_for_write(self) -> Path:
        p = Path(self._path)
        if p.is_absolute():
            return p
        return Path.cwd() / p

    @staticmethod
    def _atomic_write(file_path: Path, data: dict[str, object]) -> None:
        """Write JSON data atomically via temp file + rename."""
        content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        fd, tmp_path = tempfile.mkstemp(
            dir=file_path.parent, suffix=".tmp", prefix=".story_"
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

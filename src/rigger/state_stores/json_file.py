"""JsonFileStateStore — reads/writes EpochState to a configurable JSON file.

Config name: ``json_file``

Corpus pattern SC-1: JSON-file-based state persistence.
Sources: C1 (Anthropic), C2 (OpenAI).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from rigger._types import EpochState

logger = logging.getLogger(__name__)


class JsonFileStateStore:
    """Persists ``EpochState`` to a user-specified JSON file.

    The file path can be absolute or relative. Relative paths are resolved
    against ``project_root``. Writes are atomic (temp file + ``os.replace``).

    Args:
        path: Path to the JSON state file.
    """

    def __init__(self, path: str) -> None:
        self._path = path

    def _resolve(self, project_root: Path) -> Path:
        """Resolve the configured path against project_root."""
        p = Path(self._path)
        if p.is_absolute():
            return p
        return project_root / p

    def load(self, project_root: Path) -> EpochState:
        """Load state from the JSON file, returning defaults if missing."""
        file_path = self._resolve(project_root)
        if not file_path.exists():
            return EpochState()

        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            logger.warning("Failed to read state from %s: %s", file_path, exc)
            return EpochState()

        if not isinstance(data, dict):
            logger.warning(
                "State file %s has unexpected type %s -- using defaults",
                file_path,
                type(data).__name__,
            )
            return EpochState()

        return self._parse_state(data)

    def save(self, project_root: Path, state: EpochState) -> None:
        """Atomically write state to the JSON file."""
        file_path = self._resolve(project_root)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {
            "epoch": state.epoch,
            "completed_tasks": state.completed_tasks,
            "pending_tasks": state.pending_tasks,
            "halted": state.halted,
            "halt_reason": state.halt_reason,
            "metadata": state.metadata,
        }
        self._atomic_write(file_path, data)

    @staticmethod
    def _parse_state(data: dict[str, Any]) -> EpochState:
        """Parse a dict into EpochState, falling back to defaults on error."""
        try:
            return EpochState(
                epoch=data["epoch"],
                completed_tasks=data.get("completed_tasks", []),
                pending_tasks=data.get("pending_tasks", []),
                halted=data.get("halted", False),
                halt_reason=data.get("halt_reason", ""),
                metadata=data.get("metadata", {}),
            )
        except (KeyError, TypeError) as exc:
            logger.warning("Malformed state data: %s -- using defaults", exc)
            return EpochState()

    @staticmethod
    def _atomic_write(file_path: Path, data: dict[str, Any]) -> None:
        """Write JSON atomically via temp file + os.replace()."""
        content = json.dumps(data, indent=2).encode()
        fd, tmp_path = tempfile.mkstemp(
            dir=file_path.parent, prefix=".tmp_", suffix=".json"
        )
        try:
            os.write(fd, content)
            os.fsync(fd)
            os.close(fd)
            fd = -1
            os.replace(tmp_path, file_path)
        except BaseException:
            if fd >= 0:
                os.close(fd)
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

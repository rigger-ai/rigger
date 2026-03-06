"""Schema utilities for the .harness/ bilateral protocol.

Provides read/write functions for the bilateral filesystem protocol
between the Rigger harness loop and agent backends. All writes are
atomic (temp file + os.replace). All reads are resilient to missing
files, malformed JSON, and unknown schema versions.

Source: Task 5.3 (.harness/ Directory Schema Specification),
Task 5.4 §5 (backend resilience), Task 5.8 (atomic writes).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from rigger._types import EpochState, Task

logger = logging.getLogger(__name__)

# Protocol constants (Task 5.3 §1.1, §9.1)
HARNESS_DIR = ".harness"
TASK_FILE = "current_task.json"
STATE_FILE = "state.json"
CONSTRAINTS_FILE = "constraints.json"
PROVISIONS_FILE = "provisions.json"
SCHEMA_VERSION = "1.0"


# ─── Directory ───────────────────────────────────────────────


def ensure_harness_dir(project_root: Path) -> Path:
    """Create the .harness/ directory if it does not exist.

    Args:
        project_root: Root of the project.

    Returns:
        Path to the .harness/ directory.
    """
    harness_dir = project_root / HARNESS_DIR
    harness_dir.mkdir(parents=True, exist_ok=True)
    return harness_dir


# ─── Atomic write helper ────────────────────────────────────


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write JSON data atomically via temp file + os.replace().

    Creates a temporary file in the same directory as the target,
    writes JSON content, fsyncs, and atomically renames. Cleans up
    the temp file on failure.

    Args:
        path: Target file path. Parent directory must exist.
        data: JSON-serializable dict to write.
    """
    content = json.dumps(data, indent=2).encode()
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        os.write(fd, content)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(tmp_path, path)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


# ─── Write functions ─────────────────────────────────────────


def write_current_task(project_root: Path, task: Task) -> None:
    """Serialize Task to .harness/current_task.json.

    Args:
        project_root: Root of the project.
        task: Task to serialize.
    """
    harness_dir = ensure_harness_dir(project_root)
    data: dict[str, Any] = {
        "_schema_version": SCHEMA_VERSION,
        "id": task.id,
        "description": task.description,
        "metadata": task.metadata,
    }
    _atomic_write(harness_dir / TASK_FILE, data)


def write_state(project_root: Path, state: EpochState) -> None:
    """Serialize EpochState to .harness/state.json.

    Args:
        project_root: Root of the project.
        state: Epoch state to serialize.
    """
    harness_dir = ensure_harness_dir(project_root)
    data: dict[str, Any] = {
        "_schema_version": SCHEMA_VERSION,
        "epoch": state.epoch,
        "completed_tasks": state.completed_tasks,
        "pending_tasks": state.pending_tasks,
        "halted": state.halted,
        "halt_reason": state.halt_reason,
        "metadata": state.metadata,
    }
    _atomic_write(harness_dir / STATE_FILE, data)


def write_constraints(
    project_root: Path,
    merged_metadata: dict[str, Any],
) -> None:
    """Write or delete .harness/constraints.json.

    Writes the file when merged_metadata is non-empty. Deletes the file
    when empty, preventing stale constraints from prior epochs from
    leaking into subsequent epochs (Task 5.3 cross-exam X1).

    Args:
        project_root: Root of the project.
        merged_metadata: Already-merged constraint metadata dict.
    """
    constraints_path = project_root / HARNESS_DIR / CONSTRAINTS_FILE
    if merged_metadata:
        ensure_harness_dir(project_root)
        data: dict[str, Any] = {
            "_schema_version": SCHEMA_VERSION,
            **merged_metadata,
        }
        _atomic_write(constraints_path, data)
    elif constraints_path.exists():
        constraints_path.unlink()


# ─── Read helpers ────────────────────────────────────────────


def _read_harness_file(
    project_root: Path,
    filename: str,
    *,
    required: bool = False,
) -> dict[str, Any] | None:
    """Read a .harness/ JSON file with resilience.

    Handles missing files, malformed JSON, non-dict content, and
    unknown schema versions gracefully per Task 5.3 §4.

    Args:
        project_root: The project directory.
        filename: The file to read (e.g., "current_task.json").
        required: If True, log WARNING on missing file.

    Returns:
        Parsed dict, or None if file is missing or malformed.
    """
    path = project_root / HARNESS_DIR / filename
    if not path.exists():
        if required:
            logger.warning(".harness/%s not found -- using defaults", filename)
        return None

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        logger.error(
            ".harness/%s is malformed: %s -- treating as missing",
            filename,
            exc,
        )
        return None

    if not isinstance(data, dict):
        logger.error(
            ".harness/%s has unexpected JSON type %s -- treating as missing",
            filename,
            type(data).__name__,
        )
        return None

    # Version check (Task 5.3 §4.5)
    version = data.get("_schema_version", "")
    if version:
        major = version.split(".")[0]
        if major not in ("1",):
            logger.warning(
                ".harness/%s has unrecognized major version %s "
                "(expected 1.x) -- proceeding with best-effort read",
                filename,
                version,
            )

    return data


# ─── Read functions ──────────────────────────────────────────


def read_current_task(project_root: Path) -> Task | None:
    """Read .harness/current_task.json and return a Task.

    Returns None if the file is missing, malformed, or has missing
    required fields. Logs appropriate warnings per Task 5.3 §4.

    Args:
        project_root: Root of the project.

    Returns:
        Task if file is valid, None otherwise.
    """
    data = _read_harness_file(project_root, TASK_FILE, required=True)
    if data is None:
        return None

    try:
        return Task(
            id=data["id"],
            description=data["description"],
            metadata=data.get("metadata", {}),
        )
    except (KeyError, TypeError) as exc:
        logger.error(
            ".harness/%s missing required fields: %s -- treating as missing",
            TASK_FILE,
            exc,
        )
        return None


def read_state(project_root: Path) -> EpochState:
    """Read .harness/state.json and return EpochState.

    Always returns a valid EpochState. Falls back to initial state
    (epoch=0, empty lists) when the file is missing or malformed.
    Missing state.json and epoch=0 are semantically equivalent
    (Task 5.3 §2.2 X6).

    Args:
        project_root: Root of the project.

    Returns:
        EpochState from file or default initial state.
    """
    data = _read_harness_file(project_root, STATE_FILE, required=True)
    if data is None:
        return EpochState()

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
        logger.error(
            ".harness/%s missing required fields: %s -- using defaults",
            STATE_FILE,
            exc,
        )
        return EpochState()


def read_constraints(project_root: Path) -> dict[str, Any]:
    """Read .harness/constraints.json and return constraint metadata.

    Returns an empty dict when the file is missing (normal case: no
    dynamic restrictions) or malformed. The ``_schema_version`` field
    is stripped from the returned dict.

    Args:
        project_root: Root of the project.

    Returns:
        Constraint metadata dict, or empty dict if absent/invalid.
    """
    data = _read_harness_file(project_root, CONSTRAINTS_FILE)
    if data is None:
        return {}

    result = dict(data)
    result.pop("_schema_version", None)
    return result


# ─── Entropy partitioned files ────────────────────────────


ENTROPY_DIR = "entropy"
_LEGACY_PENDING_FILE = "pending_tasks.json"


def write_entropy_tasks(project_root: Path, tasks: list[Task]) -> Path:
    """Write entropy tasks to a partitioned file in .harness/entropy/.

    Creates ``.harness/entropy/tasks_{timestamp}_{uuid}.json`` with
    atomic write semantics. Each file is an independent partition
    that eliminates shared-mutable-file race conditions.

    Args:
        project_root: Root of the project.
        tasks: Non-empty list of entropy tasks to write.

    Returns:
        Path to the created partition file.

    Raises:
        ValueError: If tasks list is empty.
    """
    if not tasks:
        msg = "Cannot write empty entropy task list"
        raise ValueError(msg)

    entropy_dir = ensure_harness_dir(project_root) / ENTROPY_DIR
    entropy_dir.mkdir(parents=True, exist_ok=True)

    ts = int(time.time() * 1000)
    uid = uuid.uuid4().hex[:8]
    filename = f"tasks_{ts}_{uid}.json"
    target = entropy_dir / filename

    data: list[dict[str, Any]] = [
        {
            "_schema_version": SCHEMA_VERSION,
            "id": t.id,
            "description": t.description,
            "metadata": t.metadata,
        }
        for t in tasks
    ]
    _atomic_write(target, {"tasks": data})
    return target


class FilesystemEntropyTaskSource:
    """Reads entropy tasks from partitioned files in .harness/entropy/.

    On initialization, migrates legacy ``pending_tasks.json`` to
    the partitioned format and cleans up orphaned temp files.

    Partitions are read in sorted order (oldest first by filename
    timestamp). ``mark_complete()`` removes tasks from their
    partition, deleting empty partition files.
    """

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root
        self._entropy_dir = project_root / HARNESS_DIR / ENTROPY_DIR
        self._migrate_legacy()
        self._cleanup_orphans()

    def _migrate_legacy(self) -> None:
        """Migrate legacy pending_tasks.json to partitioned format."""
        legacy_path = self._project_root / HARNESS_DIR / _LEGACY_PENDING_FILE
        if not legacy_path.exists():
            return

        try:
            data = json.loads(legacy_path.read_text())
        except (json.JSONDecodeError, OSError):
            legacy_path.unlink(missing_ok=True)
            return

        tasks: list[Task] = []
        items = data if isinstance(data, list) else data.get("tasks", [])
        for item in items:
            if isinstance(item, dict) and "id" in item and "description" in item:
                tasks.append(
                    Task(
                        id=item["id"],
                        description=item["description"],
                        metadata=item.get("metadata", {}),
                    )
                )

        if tasks:
            write_entropy_tasks(self._project_root, tasks)

        legacy_path.unlink(missing_ok=True)
        logger.info("Migrated %d tasks from legacy pending_tasks.json", len(tasks))

    def _cleanup_orphans(self) -> None:
        """Remove orphaned .tmp_* files in the entropy directory."""
        if not self._entropy_dir.exists():
            return
        for tmp in self._entropy_dir.glob(".tmp_*"):
            with contextlib.suppress(OSError):
                tmp.unlink()

    def _partition_paths(self) -> list[Path]:
        """Return sorted partition file paths (oldest first)."""
        if not self._entropy_dir.exists():
            return []
        paths = sorted(self._entropy_dir.glob("tasks_*.json"))
        return paths

    def _read_partition(self, path: Path) -> list[Task]:
        """Read tasks from a single partition file."""
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Malformed entropy partition %s — skipping", path.name)
            return []

        items = data.get("tasks", []) if isinstance(data, dict) else []
        tasks: list[Task] = []
        for item in items:
            if isinstance(item, dict) and "id" in item and "description" in item:
                tasks.append(
                    Task(
                        id=item["id"],
                        description=item["description"],
                        metadata=item.get("metadata", {}),
                    )
                )
        return tasks

    def pending(self, project_root: Path) -> list[Task]:
        """Return all pending entropy tasks across partitions, oldest first."""
        tasks: list[Task] = []
        for path in self._partition_paths():
            tasks.extend(self._read_partition(path))
        return tasks

    def mark_complete(self, task_id: str, result: object = None) -> None:
        """Remove a completed task from its partition.

        Scans partitions for the task_id. If removal leaves the
        partition empty, the file is deleted. Otherwise, the
        partition is atomically rewritten.
        """
        for path in self._partition_paths():
            tasks = self._read_partition(path)
            remaining = [t for t in tasks if t.id != task_id]
            if len(remaining) == len(tasks):
                continue

            if not remaining:
                with contextlib.suppress(OSError):
                    path.unlink()
            else:
                data: list[dict[str, Any]] = [
                    {
                        "_schema_version": SCHEMA_VERSION,
                        "id": t.id,
                        "description": t.description,
                        "metadata": t.metadata,
                    }
                    for t in remaining
                ]
                _atomic_write(path, {"tasks": data})
            return

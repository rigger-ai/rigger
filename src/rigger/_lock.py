"""Lock file mechanism to prevent concurrent harness runs.

Creates ``.harness/harness.lock`` with PID, timestamp, instance ID, and
hostname.  Stale locks (dead PIDs on the same host) are automatically
cleaned.  Use ``harness_lock`` as a context manager for safe
acquire/release.

Source: Gap Analysis §C3, Task 4.3 spec.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import platform
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

from rigger._schema import HARNESS_DIR, ensure_harness_dir

logger = logging.getLogger(__name__)

LOCK_FILE = "harness.lock"


class HarnessAlreadyRunning(RuntimeError):
    """Raised when another harness instance holds the lock."""


@dataclass(frozen=True)
class LockInfo:
    """Metadata written to the lock file."""

    pid: int
    timestamp: float
    instance_id: str
    hostname: str


def _lock_path(project_root: Path) -> Path:
    """Return the path to ``.harness/harness.lock``."""
    return project_root / HARNESS_DIR / LOCK_FILE


def _pid_alive(pid: int) -> bool:
    """Check whether *pid* is alive on this host (POSIX ``kill(0)``)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we lack permission to signal it.
        return True
    return True


def _read_lock(project_root: Path) -> LockInfo | None:
    """Read an existing lock file, returning ``None`` if absent or corrupt."""
    path = _lock_path(project_root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return LockInfo(
            pid=int(data["pid"]),
            timestamp=float(data["timestamp"]),
            instance_id=str(data["instance_id"]),
            hostname=str(data["hostname"]),
        )
    except (json.JSONDecodeError, KeyError, OSError, TypeError, ValueError):
        logger.warning("Corrupt lock file at %s — treating as absent", path)
        return None


def _write_lock(project_root: Path, info: LockInfo) -> None:
    """Atomically write the lock file."""
    ensure_harness_dir(project_root)
    target = _lock_path(project_root)
    tmp = target.with_name(f".tmp_{LOCK_FILE}")
    try:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        try:
            os.write(fd, json.dumps(asdict(info), indent=2).encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(str(tmp), str(target))
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise


def acquire_lock(
    project_root: Path,
    *,
    force: bool = False,
) -> LockInfo:
    """Create ``.harness/harness.lock``, preventing concurrent runs.

    Args:
        project_root: Root of the project containing ``.harness/``.
        force: Override an existing lock (logs a warning).

    Returns:
        The ``LockInfo`` describing the newly-acquired lock.

    Raises:
        HarnessAlreadyRunning: If a live lock is held and *force* is False.
    """
    existing = _read_lock(project_root)

    if existing is not None:
        same_host = existing.hostname == platform.node()

        if force:
            logger.warning(
                "Force-overriding existing lock (pid=%d, host=%s)",
                existing.pid,
                existing.hostname,
            )
        elif same_host and _pid_alive(existing.pid):
            msg = (
                f"Another harness instance is running "
                f"(pid={existing.pid}, instance={existing.instance_id}, "
                f"started={time.ctime(existing.timestamp)}). "
                f"Use force=True to override."
            )
            raise HarnessAlreadyRunning(msg)
        elif not same_host:
            msg = (
                f"Lock held by a different host "
                f"(host={existing.hostname}, pid={existing.pid}, "
                f"instance={existing.instance_id}). "
                f"Cannot verify if PID is alive. "
                f"Use force=True to override."
            )
            raise HarnessAlreadyRunning(msg)
        else:
            # Same host, PID is dead → stale lock
            logger.warning(
                "Stale lock detected (pid=%d is dead) — acquiring",
                existing.pid,
            )

    info = LockInfo(
        pid=os.getpid(),
        timestamp=time.time(),
        instance_id=uuid.uuid4().hex,
        hostname=platform.node(),
    )
    _write_lock(project_root, info)
    return info


def release_lock(project_root: Path, lock_info: LockInfo) -> None:
    """Remove ``.harness/harness.lock`` if it matches *lock_info*.

    Only deletes the lock if the on-disk ``instance_id`` matches
    the one we hold, preventing accidental removal of another
    instance's lock.

    Args:
        project_root: Root of the project containing ``.harness/``.
        lock_info: The ``LockInfo`` returned by ``acquire_lock``.
    """
    existing = _read_lock(project_root)
    if existing is None:
        return

    if existing.instance_id != lock_info.instance_id:
        logger.warning(
            "Lock instance_id mismatch (ours=%s, on-disk=%s) — not releasing",
            lock_info.instance_id,
            existing.instance_id,
        )
        return

    try:
        _lock_path(project_root).unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Failed to remove lock file: %s", exc)


@contextmanager
def harness_lock(
    project_root: Path,
    *,
    force: bool = False,
) -> Iterator[LockInfo]:
    """Context manager that acquires the lock on entry and releases on exit.

    Args:
        project_root: Root of the project containing ``.harness/``.
        force: Override an existing lock.

    Yields:
        The ``LockInfo`` describing the held lock.

    Raises:
        HarnessAlreadyRunning: If a live lock is held and *force* is False.
    """
    info = acquire_lock(project_root, force=force)
    try:
        yield info
    finally:
        release_lock(project_root, info)

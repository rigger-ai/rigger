"""ShellCommandEntropyDetector — runs a shell command and parses JSON output.

Config name: ``shell_command``

Corpus pattern EM-1: Generic shell-based entropy scanning.
Sources: C2 (OpenAI GC agents), C18 (Fowler periodic maintenance agents).
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from rigger._types import Task

logger = logging.getLogger(__name__)


class ShellCommandEntropyDetector:
    """Runs an arbitrary shell command and parses JSON stdout as tasks.

    The command should output a JSON array of objects, each with at least
    a ``description`` field. An optional ``priority`` field is stored in
    task metadata.

    Expected JSON format::

        [{"description": "Fix stale docs", "priority": "high"}, ...]

    Args:
        command: Shell command to execute.
        timeout: Maximum seconds to wait for the command (default 120).
    """

    def __init__(self, command: str, timeout: int = 120) -> None:
        self._command = command
        self._timeout = timeout

    def scan(self, project_root: Path) -> list[Task]:
        """Run the command and parse JSON output into tasks."""
        try:
            result = subprocess.run(
                self._command,
                shell=True,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "Entropy command timed out after %ds: %s",
                self._timeout,
                self._command,
            )
            return []

        if result.returncode != 0:
            logger.warning(
                "Entropy command exited with code %d: %s\nstderr: %s",
                result.returncode,
                self._command,
                result.stderr.strip(),
            )
            return []

        return self._parse_output(result.stdout)

    def _parse_output(self, stdout: str) -> list[Task]:
        """Parse JSON array from stdout into Task objects."""
        stdout = stdout.strip()
        if not stdout:
            return []

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            logger.warning("Malformed JSON from entropy command: %s", exc)
            return []

        if not isinstance(data, list):
            logger.warning(
                "Entropy command output is %s, expected JSON array",
                type(data).__name__,
            )
            return []

        tasks: list[Task] = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                logger.warning("Skipping non-object item at index %d", i)
                continue
            description = item.get("description")
            if not description:
                logger.warning("Skipping item at index %d: missing description", i)
                continue

            metadata: dict[str, str] = {"source": "entropy_scan"}
            if "priority" in item:
                metadata["priority"] = str(item["priority"])

            tasks.append(
                Task(
                    id=f"entropy-{i}",
                    description=str(description),
                    metadata=metadata,
                )
            )

        return tasks

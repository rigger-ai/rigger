"""DocStalenessEntropyDetector — detects stale files by modification date.

Config name: ``doc_staleness``

Corpus pattern EM-4: Doc-gardening / staleness detection.
Sources: C1 (Anthropic), C2 (OpenAI doc-gardening agent).
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from rigger._types import Task

logger = logging.getLogger(__name__)

_SECONDS_PER_DAY = 86400


class DocStalenessEntropyDetector:
    """Checks file modification dates against an age threshold.

    Scans files matching the configured glob patterns and returns a
    remediation ``Task`` for each file that hasn't been modified within
    ``max_age_days``.

    Args:
        patterns: Glob patterns to match (e.g. ``["docs/**/*.md"]``).
        max_age_days: Maximum age in days before a file is considered stale
            (default 30).
    """

    def __init__(
        self,
        patterns: list[str],
        max_age_days: int = 30,
    ) -> None:
        self._patterns = list(patterns)
        self._max_age_days = max_age_days

    def scan(self, project_root: Path) -> list[Task]:
        """Find files exceeding the staleness threshold."""
        threshold = time.time() - (self._max_age_days * _SECONDS_PER_DAY)
        tasks: list[Task] = []

        for pattern in self._patterns:
            for file_path in sorted(project_root.glob(pattern)):
                if not file_path.is_file():
                    continue
                try:
                    mtime = file_path.stat().st_mtime
                except OSError as exc:
                    logger.warning("Cannot stat %s: %s", file_path, exc)
                    continue

                if mtime < threshold:
                    age_days = int((time.time() - mtime) / _SECONDS_PER_DAY)
                    last_modified = datetime.fromtimestamp(mtime, tz=UTC).strftime(
                        "%Y-%m-%d"
                    )
                    relative = file_path.relative_to(project_root)

                    tasks.append(
                        Task(
                            id=f"stale-{relative}",
                            description=(
                                f"Update {relative} "
                                f"(last modified {last_modified}, "
                                f"{age_days} days ago)"
                            ),
                            metadata={
                                "source": "entropy_scan",
                                "file": str(relative),
                                "last_modified": last_modified,
                                "age_days": age_days,
                            },
                        )
                    )

        return tasks

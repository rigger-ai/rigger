"""FileTreeContextSource — verifies a directory tree exists and reports its paths.

Config name: ``file_tree``

Corpus pattern CP-1: Initializer + progress file provisioning.
Sources: C1 (Anthropic), C2 (OpenAI).
"""

from __future__ import annotations

import logging
from pathlib import Path

from rigger._types import ProvisionResult

logger = logging.getLogger(__name__)


class FileTreeContextSource:
    """Verifies a directory tree exists and reports its file paths as context.

    Does NOT copy files — they are already in the project. This source
    validates presence and returns discovered paths as a ``ProvisionResult``.

    Args:
        root: Relative path from project root to the directory tree.
        required: If True (default), log a warning when the directory is missing.
    """

    def __init__(self, root: str, *, required: bool = True) -> None:  # noqa: D107
        self._root = root
        self._required = required

    def gather(self, project_root: Path) -> ProvisionResult:
        """Return paths to all files under the configured root directory.

        If the directory does not exist and ``required`` is True, logs a
        warning and returns an empty result. Non-required missing directories
        return silently.
        """
        tree_path = project_root / self._root

        if not tree_path.exists():
            if self._required:
                logger.warning(
                    "Required directory %s does not exist in %s",
                    self._root,
                    project_root,
                )
            return ProvisionResult()

        if not tree_path.is_dir():
            logger.warning(
                "Path %s exists but is not a directory in %s",
                self._root,
                project_root,
            )
            return ProvisionResult()

        files = sorted(p for p in tree_path.rglob("*") if p.is_file())
        return ProvisionResult(files=files)

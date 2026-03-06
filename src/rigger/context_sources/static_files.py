"""StaticFilesContextSource — copies pre-computed files into the project.

Config name: ``static_files``

Corpus pattern CP-5: Entropy/quality metadata provisioning.
Sources: C7 (Spotify), C8 (Spotify Architecture).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from rigger._types import ProvisionResult

logger = logging.getLogger(__name__)


class StaticFilesContextSource:
    """Copies pre-computed files from a configured path into the project.

    The source may be a single file or a directory. When the source is
    a directory, all files within it are copied recursively to the
    destination, preserving the relative directory structure.

    Args:
        source: Absolute or relative path to the source file or directory.
        destination: Relative path within the project root for output.
    """

    def __init__(self, source: str, destination: str) -> None:  # noqa: D107
        self._source = source
        self._destination = destination

    def gather(self, project_root: Path) -> ProvisionResult:
        """Copy source files to destination under project root, return paths.

        If the source does not exist, logs a warning and returns an
        empty result.
        """
        source_path = Path(self._source)
        if not source_path.is_absolute():
            source_path = project_root / source_path

        if not source_path.exists():
            logger.warning("Static files source %s does not exist", source_path)
            return ProvisionResult()

        dest_path = project_root / self._destination
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if source_path.is_file():
            return self._copy_file(source_path, dest_path)
        return self._copy_dir(source_path, dest_path)

    @staticmethod
    def _copy_file(source: Path, dest: Path) -> ProvisionResult:
        """Copy a single file to the destination."""
        shutil.copy2(source, dest)
        final = dest / source.name if dest.is_dir() else dest
        return ProvisionResult(files=[final])

    @staticmethod
    def _copy_dir(source: Path, dest: Path) -> ProvisionResult:
        """Copy all files from source directory to destination."""
        dest.mkdir(parents=True, exist_ok=True)
        files: list[Path] = []
        for src_file in sorted(source.rglob("*")):
            if not src_file.is_file():
                continue
            relative = src_file.relative_to(source)
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, target)
            files.append(target)
        return ProvisionResult(files=files)

"""IndependentDirManager — workspace isolation via directory copies.

Creates isolated execution environments by copying the project directory
to a temporary location. No git required. Merge copies results back
to the main root.

Source: Task 1.8 (WorkspaceManager implementations).
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from rigger._types import MergeResult, Task

logger = logging.getLogger(__name__)


class IndependentDirManager:
    """Workspace isolation via directory copies.

    Each agent works on a full copy of the project in a temp directory.
    On completion, the copy is merged back by overwriting the main root.
    No git operations — works with any project.

    Use this when git worktrees are unavailable or undesired (e.g.,
    non-git projects, CI environments without git, or when branch
    management overhead is unwanted).
    """

    def __init__(self, *, prefix: str = "rigger-") -> None:
        """Initialize the manager.

        Args:
            prefix: Prefix for temporary directory names.
        """
        self._prefix = prefix

    def create(self, main_root: Path, task: Task, branch_name: str) -> Path:
        """Copy the project to a temporary directory.

        Args:
            main_root: The main project root to copy.
            task: The task to execute (used for logging context).
            branch_name: Ignored — present for protocol compatibility.

        Returns:
            Path to the temporary copy.
        """
        tmp_parent = Path(tempfile.mkdtemp(prefix=self._prefix))
        workspace = tmp_parent / main_root.name
        shutil.copytree(main_root, workspace, symlinks=True)

        logger.debug(
            "Created workspace copy for task %s at %s",
            task.id,
            workspace,
        )
        return workspace

    def merge(self, worktree: Path, main_root: Path) -> MergeResult:
        """Copy workspace contents back to the main root.

        Overwrites files in main_root with those from the workspace.
        Does not delete files in main_root that don't exist in the
        workspace.

        Args:
            worktree: Path to the workspace copy.
            main_root: The main project root to update.

        Returns:
            MergeResult with success=True on completion.
        """
        try:
            shutil.copytree(worktree, main_root, symlinks=True, dirs_exist_ok=True)
            return MergeResult(success=True, worktree_path=worktree)
        except OSError as exc:
            return MergeResult(
                success=False,
                worktree_path=worktree,
                metadata={"error": str(exc)},
            )

    def cleanup(self, worktree: Path) -> None:
        """Remove the temporary workspace directory. Idempotent.

        Args:
            worktree: Path to the workspace to remove.
        """
        # The workspace is a subdirectory of the temp parent.
        tmp_parent = worktree.parent
        if tmp_parent.exists():
            shutil.rmtree(tmp_parent, ignore_errors=True)

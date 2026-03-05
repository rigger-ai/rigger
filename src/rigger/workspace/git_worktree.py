"""GitWorktreeManager — workspace isolation via git worktrees.

Creates isolated execution environments using ``git worktree add``.
Each parallel agent gets its own worktree with a dedicated branch.
Merge integrates changes back into the main root via ``git merge``.

Source: Task 1.13 (parallel dispatch design), Task 5.6 (validation).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from rigger._types import MergeResult, Task

logger = logging.getLogger(__name__)


def _get_branch_name(worktree: Path) -> str:
    """Extract the current branch name from a worktree."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=worktree,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _get_main_root(worktree: Path) -> Path:
    """Discover the main repo root from within a worktree.

    Uses ``git rev-parse --git-common-dir`` which returns the shared
    ``.git/`` directory of the main repo. The main root is its parent.
    This works regardless of branch name nesting depth (X3 resolution).
    """
    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=worktree,
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip()).resolve().parent


def _get_conflicting_files(repo_root: Path) -> list[str]:
    """List files with merge conflicts in the working tree."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.strip().splitlines() if f]


class GitWorktreeManager:
    """Workspace isolation via git worktrees with sequential merge.

    Each agent works on its own branch in an isolated worktree.
    On completion, the branch is merged back into the main root
    via ``git merge --no-ff``.

    WARNING: Sequential merge creates PRIORITY-COUPLING. Tasks merged
    first always succeed; later tasks bear merge conflict risk.

    Worktrees are created under ``<parent>/.rigger-worktrees/<branch_name>``.
    Minimum git version: 2.17 (for ``git worktree remove``).
    """

    def create(self, main_root: Path, task: Task, branch_name: str) -> Path:
        """Create a git worktree with a new branch.

        Args:
            main_root: The main project root (must be a git repo with
                at least one commit).
            task: The task to execute (used for logging context).
            branch_name: Branch name for the new worktree.

        Returns:
            Path to the created worktree directory.

        Raises:
            RuntimeError: If the repo has no commits.
            subprocess.CalledProcessError: If worktree creation fails.
        """
        resolved_root = main_root.resolve()

        # E8: Verify repo has at least one commit.
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=resolved_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            msg = f"Cannot create worktree: {resolved_root} has no commits."
            raise RuntimeError(msg)

        worktree_dir = resolved_root.parent / ".rigger-worktrees" / branch_name

        # X8: Ensure parent directories exist for slash-containing branch names.
        worktree_dir.parent.mkdir(parents=True, exist_ok=True)

        # E6: Clean up stale worktree/branch if exists from a previous crash.
        if worktree_dir.exists():
            subprocess.run(
                ["git", "worktree", "remove", str(worktree_dir), "--force"],
                cwd=resolved_root,
                check=False,
            )
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=resolved_root,
            check=False,
        )

        # Create worktree with new branch (strict -b, not -B).
        subprocess.run(
            ["git", "worktree", "add", str(worktree_dir), "-b", branch_name],
            cwd=resolved_root,
            check=True,
        )

        # E2: Initialize submodules if present.
        if (worktree_dir / ".gitmodules").exists():
            subprocess.run(
                ["git", "submodule", "update", "--init", "--recursive"],
                cwd=worktree_dir,
                check=True,
            )

        logger.debug(
            "Created worktree for task %s at %s (branch: %s)",
            task.id,
            worktree_dir,
            branch_name,
        )
        return worktree_dir

    def merge(self, worktree: Path, main_root: Path) -> MergeResult:
        """Merge worktree branch into main_root via ``git merge --no-ff``.

        On conflict, aborts the merge and returns conflict details.

        Args:
            worktree: Path to the worktree to merge from.
            main_root: The main project root to merge into.

        Returns:
            MergeResult with success status and any conflict information.
        """
        branch = _get_branch_name(worktree)
        try:
            subprocess.run(
                ["git", "merge", branch, "--no-ff"],
                cwd=main_root,
                check=True,
                capture_output=True,
                text=True,
            )
            return MergeResult(success=True, merged_commits=[branch])
        except subprocess.CalledProcessError:
            conflicts = _get_conflicting_files(main_root)
            subprocess.run(
                ["git", "merge", "--abort"],
                cwd=main_root,
                check=False,
            )
            return MergeResult(
                success=False,
                conflicts=conflicts,
                worktree_path=worktree,
            )

    def cleanup(self, worktree: Path) -> None:
        """Remove worktree and its branch. Idempotent.

        Args:
            worktree: Path to the worktree to remove.
        """
        if not worktree.exists():
            return

        branch = _get_branch_name(worktree)

        # X3: Discover main repo root reliably.
        main_root = _get_main_root(worktree)

        # E11: Unlock if locked (no-op if not locked).
        subprocess.run(
            ["git", "worktree", "unlock", str(worktree)],
            cwd=main_root,
            check=False,
        )
        subprocess.run(
            ["git", "worktree", "remove", str(worktree), "--force"],
            cwd=main_root,
            check=False,
        )
        subprocess.run(
            ["git", "branch", "-D", branch],
            cwd=main_root,
            check=False,
        )

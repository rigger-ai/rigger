"""IndependentBranchManager — branch-per-task, push as PR, no local merge.

The corpus-dominant WorkspaceManager pattern (4/6 sources: C2, C6, C14, C15).
Each agent works on its own branch in an isolated worktree. On completion,
the branch is pushed to the remote and optionally a PR is created via
``gh pr create``. No local merge into main_root.

Source: Task 1.13 §1.3, Task 5.6 §5.2, Finding 7.19, Gap Analysis §A6.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

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


class IndependentBranchManager:
    """Default WorkspaceManager: branch-per-task, push as PR.

    Each agent works on its own branch in an isolated worktree.
    On completion, the branch is pushed to the remote. No local merge
    into main_root. PRs are merged by human review or CI.

    Matches: C2 (OpenAI), C6 (Spotify), C14 (Composio), C15 (Open SWE).
    This is the corpus-dominant pattern (4/6 parallel sources).

    Worktrees are created under ``<parent>/.rigger-worktrees/<branch_name>``.
    Minimum git version: 2.17 (for ``git worktree remove``).
    """

    def __init__(
        self,
        *,
        remote: str = "origin",
        create_pr: bool = True,
        cleanup_branch: bool = False,
    ) -> None:
        """Initialize the manager.

        Args:
            remote: Git remote name for pushing branches.
            create_pr: Whether to create a GitHub PR after pushing via
                ``gh pr create``. Non-fatal if ``gh`` is unavailable.
            cleanup_branch: Whether to delete the local branch on cleanup.
                Default False since branches are the deliverable (PRs).
        """
        self._remote = remote
        self._create_pr = create_pr
        self._cleanup_branch = cleanup_branch

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
        """Push branch to remote. No local merge.

        Pushes the worktree's branch to the configured remote. Optionally
        creates a GitHub PR via ``gh pr create``. PR creation failure is
        non-fatal since the branch is already pushed.

        Args:
            worktree: Path to the worktree to push from.
            main_root: The main project root (unused — no local merge).

        Returns:
            MergeResult with success status and diagnostic metadata.
        """
        branch = _get_branch_name(worktree)
        try:
            subprocess.run(
                ["git", "push", self._remote, branch],
                cwd=worktree,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            return MergeResult(
                success=False,
                worktree_path=worktree,
                metadata={"stderr": e.stderr, "returncode": e.returncode},
            )

        metadata: dict[str, Any] = {}
        if self._create_pr:
            try:
                pr_result = subprocess.run(
                    ["gh", "pr", "create", "--head", branch, "--fill"],
                    cwd=worktree,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                metadata["pr_url"] = pr_result.stdout.strip()
            except FileNotFoundError:
                logger.warning("gh CLI not found; skipping PR creation for %s", branch)
            except subprocess.CalledProcessError as e:
                logger.warning(
                    "PR creation failed for %s: %s", branch, e.stderr.strip()
                )

        return MergeResult(success=True, metadata=metadata)

    def cleanup(self, worktree: Path) -> None:
        """Remove worktree and optionally its branch. Idempotent.

        By default, preserves the branch since it's the deliverable
        (pushed as a PR). Set ``cleanup_branch=True`` to also delete it.

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

        if self._cleanup_branch:
            subprocess.run(
                ["git", "branch", "-D", branch],
                cwd=main_root,
                check=False,
            )

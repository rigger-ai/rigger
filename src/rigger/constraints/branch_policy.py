"""BranchPolicyConstraint — validates branch naming and protects main branches.

Config name: ``branch_policy``

Corpus pattern AC-5: Branch naming convention and protected branch enforcement.
Sources: C2 (OpenAI), C6 (GitHub).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from rigger._types import VerifyAction, VerifyResult

logger = logging.getLogger(__name__)

_DEFAULT_PROTECTED = ["main", "master"]


class BranchPolicyConstraint:
    """Validates branch naming convention and blocks commits to protected branches.

    Returns ``BLOCK`` if the current branch is protected, or if a
    ``required_prefix`` is configured and the branch doesn't match.

    Args:
        protected_branches: Branch names that must not receive direct commits
            (default: ``["main", "master"]``).
        required_prefix: If set, non-protected branches must start with this
            prefix (e.g. ``"task/"`` or ``"feature/"``).
    """

    def __init__(
        self,
        protected_branches: list[str] | None = None,
        required_prefix: str | None = None,
    ) -> None:
        self._protected = (
            list(protected_branches)
            if protected_branches is not None
            else list(_DEFAULT_PROTECTED)
        )
        self._required_prefix = required_prefix

    def check(self, project_root: Path) -> VerifyResult:
        """Check the current git branch against the policy."""
        branch = self._get_current_branch(project_root)
        if branch is None:
            return VerifyResult(
                passed=False,
                action=VerifyAction.BLOCK,
                message="Could not determine current git branch.",
                details={"project_root": str(project_root)},
            )

        if branch in self._protected:
            return VerifyResult(
                passed=False,
                action=VerifyAction.BLOCK,
                message=(
                    f"Direct commits to protected branch '{branch}' are not allowed."
                ),
                details={
                    "branch": branch,
                    "protected_branches": self._protected,
                },
            )

        if self._required_prefix and not branch.startswith(self._required_prefix):
            return VerifyResult(
                passed=False,
                action=VerifyAction.BLOCK,
                message=(
                    f"Branch '{branch}' does not match required prefix "
                    f"'{self._required_prefix}'."
                ),
                details={
                    "branch": branch,
                    "required_prefix": self._required_prefix,
                },
            )

        return VerifyResult(
            passed=True,
            message=f"Branch '{branch}' satisfies policy.",
            details={"branch": branch},
        )

    @staticmethod
    def _get_current_branch(project_root: Path) -> str | None:
        """Read the current git branch name via ``git rev-parse``."""
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

        if proc.returncode != 0:
            return None

        return proc.stdout.strip() or None

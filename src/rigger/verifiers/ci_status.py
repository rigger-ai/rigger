"""CiStatusVerifier — checks CI pipeline status on a branch.

Config name: ``ci_status``

Corpus pattern FL-6: CI pipeline as verifier gate.
Sources: C2 (OpenAI), C6 (GitHub), C14 (Composio), C9 (Osmani).
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from rigger._types import TaskResult, VerifyAction, VerifyResult

logger = logging.getLogger(__name__)


class CiStatusVerifier:
    """Checks GitHub Actions / CI pipeline status via ``gh`` CLI.

    Polls CI status for the current (or configured) branch. All checks
    passed maps to ACCEPT, failed maps to ``action_on_fail``, pending
    triggers a polling loop with configurable backoff.

    Args:
        branch: Branch to check (default: infer from current HEAD).
        timeout: Maximum seconds to poll (default 600).
        poll_interval: Seconds between polls (default 30).
        action_on_fail: VerifyAction when CI fails (default RETRY).
    """

    def __init__(
        self,
        branch: str | None = None,
        timeout: int = 600,
        poll_interval: int = 30,
        action_on_fail: str = "retry",
    ) -> None:
        self._branch = branch
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._action_on_fail = VerifyAction(action_on_fail)

    def verify(self, project_root: Path, result: TaskResult) -> VerifyResult:
        """Poll CI status until terminal state or timeout."""
        branch = self._branch or self._current_branch(project_root)
        if not branch:
            return VerifyResult(
                passed=False,
                action=VerifyAction.BLOCK,
                message="Could not determine current branch.",
            )

        deadline = time.monotonic() + self._timeout

        while True:
            status = self._check_status(project_root, branch)

            if status == "success":
                return VerifyResult(
                    passed=True,
                    message=f"All CI checks passed on branch '{branch}'.",
                    details={"branch": branch, "ci_status": "success"},
                )

            if status == "failure":
                logs = self._get_failure_logs(project_root, branch)
                return VerifyResult(
                    passed=False,
                    action=self._action_on_fail,
                    message=f"CI failed on branch '{branch}'.\n{logs}",
                    details={
                        "branch": branch,
                        "ci_status": "failure",
                        "logs": logs,
                    },
                )

            # status is "pending" or unknown
            if time.monotonic() + self._poll_interval > deadline:
                return VerifyResult(
                    passed=False,
                    action=self._action_on_fail,
                    message=(
                        f"CI still pending on branch '{branch}' "
                        f"after {self._timeout}s timeout."
                    ),
                    details={
                        "branch": branch,
                        "ci_status": "timeout",
                        "timeout": self._timeout,
                    },
                )

            logger.debug(
                "CI pending on '%s', polling again in %ds",
                branch,
                self._poll_interval,
            )
            time.sleep(self._poll_interval)

    @staticmethod
    def _current_branch(project_root: Path) -> str | None:
        """Get the current git branch name."""
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode == 0:
                return proc.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    @staticmethod
    def _check_status(project_root: Path, branch: str) -> str:
        """Query CI status via ``gh pr checks`` or ``gh run list``."""
        try:
            proc = subprocess.run(
                [
                    "gh",
                    "run",
                    "list",
                    "--branch",
                    branch,
                    "--limit",
                    "1",
                    "--json",
                    "status,conclusion",
                ],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0:
                return "pending"

            import json

            runs = json.loads(proc.stdout)
            if not runs:
                return "pending"

            run = runs[0]
            if run.get("status") != "completed":
                return "pending"

            conclusion = run.get("conclusion", "")
            if conclusion == "success":
                return "success"
            return "failure"

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "pending"

    @staticmethod
    def _get_failure_logs(project_root: Path, branch: str) -> str:
        """Fetch CI failure logs for agent consumption."""
        try:
            proc = subprocess.run(
                [
                    "gh",
                    "run",
                    "list",
                    "--branch",
                    branch,
                    "--limit",
                    "1",
                    "--json",
                    "databaseId",
                ],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0:
                return "Could not fetch CI logs."

            import json

            runs = json.loads(proc.stdout)
            if not runs:
                return "No CI runs found."

            run_id = runs[0].get("databaseId", "")
            if not run_id:
                return "Could not determine run ID."

            log_proc = subprocess.run(
                ["gh", "run", "view", str(run_id), "--log-failed"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if log_proc.returncode == 0 and log_proc.stdout.strip():
                return log_proc.stdout.strip()

            return "CI run failed. Use `gh run view` for details."

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "Could not fetch CI logs."

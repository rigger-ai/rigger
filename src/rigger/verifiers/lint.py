"""LintVerifier — runs a linter command and checks for errors.

Config name: ``lint``

Corpus pattern FL-2: Lint/static-analysis as verifier gate.
Sources: C1 (Anthropic), C6 (GitHub), C2 (OpenAI), C9 (Osmani).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from rigger._types import TaskResult, VerifyAction, VerifyResult

logger = logging.getLogger(__name__)


class LintVerifier:
    """Runs a linter command; zero errors means ACCEPT, errors means RETRY.

    Captures stdout/stderr and reports error count in ``VerifyResult.details``.

    Args:
        command: Linter command to run (as a list of args).
        timeout: Maximum seconds to wait (default 120).
        action_on_fail: VerifyAction when linting fails (default RETRY).
    """

    def __init__(
        self,
        command: list[str],
        timeout: int = 120,
        action_on_fail: str = "retry",
    ) -> None:
        self._command = command
        self._timeout = timeout
        self._action_on_fail = VerifyAction(action_on_fail)

    def verify(self, project_root: Path, result: TaskResult) -> VerifyResult:
        """Run the linter and return a VerifyResult based on exit code."""
        try:
            proc = subprocess.run(
                self._command,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return VerifyResult(
                passed=False,
                action=self._action_on_fail,
                message=f"Linter timed out after {self._timeout}s",
                details={
                    "stdout": (exc.stdout or b"").decode(errors="replace")
                    if isinstance(exc.stdout, bytes)
                    else (exc.stdout or ""),
                    "stderr": (exc.stderr or b"").decode(errors="replace")
                    if isinstance(exc.stderr, bytes)
                    else (exc.stderr or ""),
                    "timeout": self._timeout,
                },
            )
        except FileNotFoundError:
            return VerifyResult(
                passed=False,
                action=VerifyAction.BLOCK,
                message=f"Linter not found: {self._command[0]}",
                details={"command": self._command},
            )

        if proc.returncode == 0:
            return VerifyResult(
                passed=True,
                message="Lint check passed.",
                details={
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "returncode": proc.returncode,
                },
            )

        output = (proc.stdout + "\n" + proc.stderr).strip()
        error_count = self._count_errors(output)

        return VerifyResult(
            passed=False,
            action=self._action_on_fail,
            message=self._format_failure(output, error_count),
            details={
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "returncode": proc.returncode,
                "error_count": error_count,
            },
        )

    @staticmethod
    def _count_errors(output: str) -> int:
        """Count error lines in linter output.

        Heuristic: each non-empty line in the output is one error/warning.
        """
        return sum(1 for line in output.splitlines() if line.strip())

    @staticmethod
    def _format_failure(output: str, error_count: int) -> str:
        """Format lint violations for agent consumption."""
        parts = [f"Lint check failed ({error_count} issue(s)):"]
        if output:
            parts.append(output)
        parts.append("\nFix the lint issues above and the harness will re-verify.")
        return "\n".join(parts)

"""TestSuiteVerifier — runs a shell command and determines pass/fail from exit code.

Config name: ``test_suite``

Corpus pattern FL-1: Test suite as verifier gate.
Sources: C1 (Anthropic), C3 (Anthropic Quickstart), C9 (Osmani), C12 (SWE-agent).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from rigger._types import TaskResult, VerifyAction, VerifyResult

logger = logging.getLogger(__name__)


class TestSuiteVerifier:
    """Runs a shell command (pytest, npm test, etc.); pass/fail from exit code.

    Exit code 0 maps to ACCEPT. Non-zero maps to ``action_on_fail``
    (default RETRY). Captures stdout/stderr in ``VerifyResult.details``.

    Args:
        command: Shell command to run (as a list of args).
        timeout: Maximum seconds to wait for the command (default 300).
        action_on_fail: VerifyAction when the command fails (default RETRY).
    """

    def __init__(
        self,
        command: list[str],
        timeout: int = 300,
        action_on_fail: str = "retry",
    ) -> None:
        self._command = command
        self._timeout = timeout
        self._action_on_fail = VerifyAction(action_on_fail)

    def verify(self, project_root: Path, result: TaskResult) -> VerifyResult:
        """Run the test command and return a VerifyResult based on exit code."""
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
                message=f"Command timed out after {self._timeout}s",
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
                message=f"Command not found: {self._command[0]}",
                details={"command": self._command},
            )

        if proc.returncode == 0:
            return VerifyResult(
                passed=True,
                message="All tests passed.",
                details={
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "returncode": proc.returncode,
                },
            )

        return VerifyResult(
            passed=False,
            action=self._action_on_fail,
            message=self._format_failure(proc),
            details={
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "returncode": proc.returncode,
            },
        )

    @staticmethod
    def _format_failure(proc: subprocess.CompletedProcess[str]) -> str:
        """Format failure output for agent consumption."""
        parts: list[str] = [f"Tests failed (exit code {proc.returncode})."]
        output = (proc.stdout + "\n" + proc.stderr).strip()
        if output:
            parts.append(output)
        return "\n".join(parts)

"""RatchetVerifier — runs a sequence of verification steps in order.

Config name: ``ratchet``

Corpus pattern FL-10: Ratcheting test-then-commit pipeline.
Sources: C9 (Osmani), C16 (Mason), C8 (Spotify), C12 (SWE-agent).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from rigger._types import TaskResult, VerifyAction, VerifyResult

logger = logging.getLogger(__name__)


class RatchetVerifier:
    """Runs a pipeline of commands in sequence; ACCEPT only when all pass.

    Each step is a ``{command, name}`` pair. Stops at the first failure
    and returns RETRY with the failure output. ACCEPT only when every
    step succeeds.

    Args:
        steps: List of step dicts, each with ``command`` (list[str]) and
            ``name`` (str) keys.
        timeout: Maximum seconds per step (default 600).
    """

    def __init__(
        self,
        steps: list[dict[str, Any]],
        timeout: int = 600,
    ) -> None:
        self._steps = steps
        self._timeout = timeout

    def verify(self, project_root: Path, result: TaskResult) -> VerifyResult:
        """Run each step in sequence; RETRY on first failure, ACCEPT on all-green."""
        step_results: dict[str, bool] = {}
        failure_messages: list[str] = []

        for step in self._steps:
            name = step.get("name", "unnamed")
            command = step.get("command", [])
            if not command:
                logger.warning("Skipping step '%s' with empty command", name)
                continue

            passed, output = self._run_step(project_root, command, name)
            step_results[name] = passed

            if not passed:
                failure_messages.append(f"{name.upper()} FAILED:\n{output}")

        all_passed = bool(step_results) and all(step_results.values())

        return VerifyResult(
            passed=all_passed,
            action=VerifyAction.ACCEPT if all_passed else VerifyAction.RETRY,
            message=(
                "All checks passed." if all_passed else "\n\n".join(failure_messages)
            ),
            details={
                "step_results": step_results,
            },
        )

    def _run_step(
        self,
        project_root: Path,
        command: list[str],
        name: str,
    ) -> tuple[bool, str]:
        """Run a single pipeline step; return (passed, output)."""
        try:
            proc = subprocess.run(
                command,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            return False, f"{name} timed out after {self._timeout}s"
        except FileNotFoundError:
            return False, f"Command not found: {command[0]}"

        if proc.returncode == 0:
            return True, ""

        return False, (proc.stdout + "\n" + proc.stderr).strip()

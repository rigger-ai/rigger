"""ContainerTestVerifier — runs tests inside a Harbor container for verification."""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rigger._types import TaskResult, VerifyAction, VerifyResult

logger = logging.getLogger(__name__)


class ContainerTestVerifier:
    """Verifier that executes a test command inside the Harbor container.

    Runs ``test_command`` via ``environment.exec()``, maps exit code 0 to
    ACCEPT and non-zero to RETRY with truncated failure output written to
    ``.harness/feedback.json`` for the next dispatch cycle.

    Args:
        environment: Harbor environment with ``exec()`` coroutine.
        test_command: Shell command string to run inside the container.
        timeout: Max seconds for the test command (default 300).
        cwd: Working directory inside the container (default "/testbed").
        max_output_chars: Truncation limit for test output in feedback (default 4000).
    """

    def __init__(
        self,
        environment: object,
        test_command: str,
        *,
        timeout: int = 300,
        cwd: str = "/testbed",
        max_output_chars: int = 4000,
    ) -> None:
        self._env = environment
        self._test_command = test_command
        self._timeout = timeout
        self._cwd = cwd
        self._max_output_chars = max_output_chars

    def verify(self, project_root: Path, result: TaskResult) -> VerifyResult:
        """Run the test command in the container and return a VerifyResult."""
        try:
            exec_result = self._run_async(
                self._env.exec(
                    self._test_command,
                    cwd=self._cwd,
                    timeout_sec=self._timeout,
                )
            )
        except TimeoutError:
            return VerifyResult(
                passed=False,
                action=VerifyAction.RETRY,
                message=f"Test command timed out after {self._timeout}s",
            )
        except Exception as exc:
            logger.warning("Container test execution failed: %s", exc)
            return VerifyResult(
                passed=False,
                action=VerifyAction.RETRY,
                message=f"Test execution error: {exc}",
            )

        if exec_result.return_code == 0:
            self._remove_feedback(project_root)
            return VerifyResult(
                passed=True,
                message="Tests passed.",
                details={
                    "return_code": 0,
                    "stdout_tail": (exec_result.stdout or "")[-500:],
                },
            )

        self._write_feedback(project_root, exec_result)
        return VerifyResult(
            passed=False,
            action=VerifyAction.RETRY,
            message=self._format_failure(exec_result),
            details={
                "return_code": exec_result.return_code,
                "stdout_tail": (exec_result.stdout or "")[-1000:],
            },
        )

    def _run_async(self, coro: object) -> object:
        """Run an async coroutine from a sync context when the event loop is running."""
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=self._timeout + 30)

    def _write_feedback(self, project_root: Path, exec_result: object) -> None:
        """Write .harness/feedback.json with truncated test output."""
        harness_dir = project_root / ".harness"
        harness_dir.mkdir(parents=True, exist_ok=True)

        output = (exec_result.stdout or "") + "\n" + (exec_result.stderr or "")
        output = output.strip()
        if len(output) > self._max_output_chars:
            output = output[-self._max_output_chars :]

        feedback = {
            "test_command": self._test_command,
            "return_code": exec_result.return_code,
            "output": output,
        }
        (harness_dir / "feedback.json").write_text(
            json.dumps(feedback, indent=2), encoding="utf-8"
        )

    def _remove_feedback(self, project_root: Path) -> None:
        """Remove .harness/feedback.json on success to prevent stale feedback."""
        feedback_path = project_root / ".harness" / "feedback.json"
        if feedback_path.exists():
            feedback_path.unlink()

    def _format_failure(self, exec_result: object) -> str:
        """Format failure output for logging/VerifyResult message."""
        output = (exec_result.stdout or "") + "\n" + (exec_result.stderr or "")
        output = output.strip()
        if len(output) > 1000:
            output = output[-1000:]
        return f"Tests failed (exit code {exec_result.return_code}).\n{output}"

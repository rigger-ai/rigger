"""Tests for LintVerifier."""

from __future__ import annotations

from pathlib import Path

import pytest

from rigger._types import TaskResult, VerifyAction
from rigger.verifiers.lint import LintVerifier


@pytest.fixture
def result() -> TaskResult:
    return TaskResult(task_id="t1", status="success")


class TestPassingLint:
    def test_accept_on_clean_lint(self, tmp_path: Path, result: TaskResult):
        v = LintVerifier(command=["true"])
        vr = v.verify(tmp_path, result)
        assert vr.passed is True
        assert vr.action == VerifyAction.ACCEPT

    def test_message_on_pass(self, tmp_path: Path, result: TaskResult):
        v = LintVerifier(command=["true"])
        vr = v.verify(tmp_path, result)
        assert "passed" in vr.message.lower()


class TestFailingLint:
    def test_retry_on_lint_errors(self, tmp_path: Path, result: TaskResult):
        v = LintVerifier(command=["false"])
        vr = v.verify(tmp_path, result)
        assert vr.passed is False
        assert vr.action == VerifyAction.RETRY

    def test_error_count_in_details(self, tmp_path: Path, result: TaskResult):
        # Use a command that outputs error-like lines
        v = LintVerifier(command=["echo", "error: something\nerror: other"])
        # echo always exits 0, so use a script that fails with output
        script = tmp_path / "lint.sh"
        script.write_text(
            "#!/bin/sh\n"
            "echo 'src/foo.py:1: E001 bad'\n"
            "echo 'src/bar.py:2: E002 worse'\n"
            "exit 1\n"
        )
        script.chmod(0o755)
        v = LintVerifier(command=[str(script)])
        vr = v.verify(tmp_path, result)
        assert vr.details["error_count"] == 2

    def test_custom_action_on_fail(self, tmp_path: Path, result: TaskResult):
        v = LintVerifier(command=["false"], action_on_fail="block")
        vr = v.verify(tmp_path, result)
        assert vr.action == VerifyAction.BLOCK

    def test_failure_message_includes_fix_hint(
        self, tmp_path: Path, result: TaskResult
    ):
        script = tmp_path / "lint.sh"
        script.write_text("#!/bin/sh\necho 'error'\nexit 1\n")
        script.chmod(0o755)
        v = LintVerifier(command=[str(script)])
        vr = v.verify(tmp_path, result)
        assert "re-verify" in vr.message.lower()


class TestTimeout:
    def test_timeout_returns_failure(self, tmp_path: Path, result: TaskResult):
        v = LintVerifier(command=["sleep", "10"], timeout=1)
        vr = v.verify(tmp_path, result)
        assert vr.passed is False
        assert "timed out" in vr.message.lower()


class TestCommandNotFound:
    def test_missing_command_blocks(self, tmp_path: Path, result: TaskResult):
        v = LintVerifier(command=["nonexistent_linter_xyz"])
        vr = v.verify(tmp_path, result)
        assert vr.passed is False
        assert vr.action == VerifyAction.BLOCK


class TestProtocolConformance:
    def test_satisfies_verifier_protocol(self):
        from rigger._protocols import Verifier

        v: Verifier = LintVerifier(command=["true"])
        assert hasattr(v, "verify")

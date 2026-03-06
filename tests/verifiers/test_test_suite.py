"""Tests for TestSuiteVerifier."""

from __future__ import annotations

from pathlib import Path

import pytest

from rigger._types import TaskResult, VerifyAction
from rigger.verifiers.test_suite import TestSuiteVerifier


@pytest.fixture
def result() -> TaskResult:
    return TaskResult(task_id="t1", status="success")


class TestPassingCommand:
    def test_accept_on_zero_exit(self, tmp_path: Path, result: TaskResult):
        v = TestSuiteVerifier(command=["true"])
        vr = v.verify(tmp_path, result)
        assert vr.passed is True
        assert vr.action == VerifyAction.ACCEPT

    def test_stdout_in_details(self, tmp_path: Path, result: TaskResult):
        v = TestSuiteVerifier(command=["echo", "hello"])
        vr = v.verify(tmp_path, result)
        assert "hello" in vr.details["stdout"]


class TestFailingCommand:
    def test_retry_on_nonzero_exit(self, tmp_path: Path, result: TaskResult):
        v = TestSuiteVerifier(command=["false"])
        vr = v.verify(tmp_path, result)
        assert vr.passed is False
        assert vr.action == VerifyAction.RETRY

    def test_custom_action_on_fail(self, tmp_path: Path, result: TaskResult):
        v = TestSuiteVerifier(command=["false"], action_on_fail="block")
        vr = v.verify(tmp_path, result)
        assert vr.passed is False
        assert vr.action == VerifyAction.BLOCK

    def test_failure_message_contains_exit_code(
        self, tmp_path: Path, result: TaskResult
    ):
        v = TestSuiteVerifier(command=["false"])
        vr = v.verify(tmp_path, result)
        assert "exit code" in vr.message

    def test_returncode_in_details(self, tmp_path: Path, result: TaskResult):
        v = TestSuiteVerifier(command=["false"])
        vr = v.verify(tmp_path, result)
        assert vr.details["returncode"] != 0


class TestTimeout:
    def test_timeout_returns_failure(self, tmp_path: Path, result: TaskResult):
        v = TestSuiteVerifier(command=["sleep", "10"], timeout=1)
        vr = v.verify(tmp_path, result)
        assert vr.passed is False
        assert "timed out" in vr.message

    def test_timeout_uses_configured_action(self, tmp_path: Path, result: TaskResult):
        v = TestSuiteVerifier(
            command=["sleep", "10"], timeout=1, action_on_fail="block"
        )
        vr = v.verify(tmp_path, result)
        assert vr.action == VerifyAction.BLOCK


class TestCommandNotFound:
    def test_missing_command_blocks(self, tmp_path: Path, result: TaskResult):
        v = TestSuiteVerifier(command=["nonexistent_cmd_xyz"])
        vr = v.verify(tmp_path, result)
        assert vr.passed is False
        assert vr.action == VerifyAction.BLOCK
        assert "not found" in vr.message.lower()


class TestActionRouting:
    def test_accept_action(self, tmp_path: Path, result: TaskResult):
        v = TestSuiteVerifier(command=["true"])
        vr = v.verify(tmp_path, result)
        assert vr.action == VerifyAction.ACCEPT

    def test_retry_action(self, tmp_path: Path, result: TaskResult):
        v = TestSuiteVerifier(command=["false"])
        vr = v.verify(tmp_path, result)
        assert vr.action == VerifyAction.RETRY

    def test_escalate_action(self, tmp_path: Path, result: TaskResult):
        v = TestSuiteVerifier(command=["false"], action_on_fail="escalate")
        vr = v.verify(tmp_path, result)
        assert vr.action == VerifyAction.ESCALATE


class TestProtocolConformance:
    def test_satisfies_verifier_protocol(self):
        from rigger._protocols import Verifier

        v: Verifier = TestSuiteVerifier(command=["true"])
        assert hasattr(v, "verify")

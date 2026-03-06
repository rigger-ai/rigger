"""Integration tests for Verifier implementations against real subprocesses."""

from __future__ import annotations

from rigger._types import TaskResult, VerifyAction
from rigger.verifiers import LintVerifier, RatchetVerifier, TestSuiteVerifier


def test_test_suite_real_pass(git_project):
    v = TestSuiteVerifier(command=["bash", "-c", "exit 0"])
    result = v.verify(git_project, TaskResult(task_id="t1", status="success"))

    assert result.passed
    assert result.action == VerifyAction.ACCEPT


def test_test_suite_real_fail(git_project):
    v = TestSuiteVerifier(command=["bash", "-c", "echo 'FAIL: test_foo'; exit 1"])
    result = v.verify(git_project, TaskResult(task_id="t1", status="success"))

    assert not result.passed
    assert result.action == VerifyAction.RETRY


def test_lint_verifier_real_command(git_project):
    v = LintVerifier(command=["bash", "-c", "echo 'src/foo.py:1: E001 error'; exit 1"])
    result = v.verify(git_project, TaskResult(task_id="t1", status="success"))

    assert not result.passed
    assert "error_count" in result.details
    assert result.details["error_count"] >= 1


def test_ratchet_pipeline(git_project):
    v = RatchetVerifier(
        steps=[
            {"name": "format", "command": ["bash", "-c", "exit 0"]},
            {"name": "lint", "command": ["bash", "-c", "exit 0"]},
            {"name": "test", "command": ["bash", "-c", "exit 0"]},
        ]
    )
    result = v.verify(git_project, TaskResult(task_id="t1", status="success"))

    assert result.passed
    assert result.action == VerifyAction.ACCEPT
    assert result.details["step_results"] == {
        "format": True,
        "lint": True,
        "test": True,
    }

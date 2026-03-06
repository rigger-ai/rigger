"""Tests for RatchetVerifier."""

from __future__ import annotations

from pathlib import Path

import pytest

from rigger._types import TaskResult, VerifyAction
from rigger.verifiers.ratchet import RatchetVerifier


@pytest.fixture
def result() -> TaskResult:
    return TaskResult(task_id="t1", status="success")


@pytest.fixture
def passing_steps(tmp_path: Path) -> list[dict]:
    return [
        {"name": "tests", "command": ["true"]},
        {"name": "typecheck", "command": ["true"]},
        {"name": "lint", "command": ["true"]},
    ]


@pytest.fixture
def mixed_steps(tmp_path: Path) -> list[dict]:
    return [
        {"name": "tests", "command": ["true"]},
        {"name": "typecheck", "command": ["false"]},
        {"name": "lint", "command": ["true"]},
    ]


class TestAllPassing:
    def test_accept_when_all_pass(
        self, tmp_path: Path, result: TaskResult, passing_steps: list[dict]
    ):
        v = RatchetVerifier(steps=passing_steps)
        vr = v.verify(tmp_path, result)
        assert vr.passed is True
        assert vr.action == VerifyAction.ACCEPT

    def test_step_results_in_details(
        self, tmp_path: Path, result: TaskResult, passing_steps: list[dict]
    ):
        v = RatchetVerifier(steps=passing_steps)
        vr = v.verify(tmp_path, result)
        sr = vr.details["step_results"]
        assert sr["tests"] is True
        assert sr["typecheck"] is True
        assert sr["lint"] is True


class TestPartialFailure:
    def test_retry_on_any_failure(
        self, tmp_path: Path, result: TaskResult, mixed_steps: list[dict]
    ):
        v = RatchetVerifier(steps=mixed_steps)
        vr = v.verify(tmp_path, result)
        assert vr.passed is False
        assert vr.action == VerifyAction.RETRY

    def test_failure_message_names_step(
        self, tmp_path: Path, result: TaskResult, mixed_steps: list[dict]
    ):
        v = RatchetVerifier(steps=mixed_steps)
        vr = v.verify(tmp_path, result)
        assert "TYPECHECK FAILED" in vr.message

    def test_passing_steps_recorded(
        self, tmp_path: Path, result: TaskResult, mixed_steps: list[dict]
    ):
        v = RatchetVerifier(steps=mixed_steps)
        vr = v.verify(tmp_path, result)
        sr = vr.details["step_results"]
        assert sr["tests"] is True
        assert sr["typecheck"] is False


class TestTimeout:
    def test_timeout_per_step(self, tmp_path: Path, result: TaskResult):
        steps = [{"name": "slow", "command": ["sleep", "10"]}]
        v = RatchetVerifier(steps=steps, timeout=1)
        vr = v.verify(tmp_path, result)
        assert vr.passed is False
        assert "timed out" in vr.message.lower()


class TestCommandNotFound:
    def test_missing_command_fails_step(self, tmp_path: Path, result: TaskResult):
        steps = [{"name": "missing", "command": ["nonexistent_cmd_xyz"]}]
        v = RatchetVerifier(steps=steps)
        vr = v.verify(tmp_path, result)
        assert vr.passed is False
        assert "not found" in vr.message.lower()


class TestEmptySteps:
    def test_no_steps_fails(self, tmp_path: Path, result: TaskResult):
        v = RatchetVerifier(steps=[])
        vr = v.verify(tmp_path, result)
        assert vr.passed is False

    def test_empty_command_skipped(self, tmp_path: Path, result: TaskResult):
        steps = [{"name": "empty", "command": []}]
        v = RatchetVerifier(steps=steps)
        vr = v.verify(tmp_path, result)
        assert vr.passed is False


class TestProtocolConformance:
    def test_satisfies_verifier_protocol(self):
        from rigger._protocols import Verifier

        v: Verifier = RatchetVerifier(steps=[{"name": "x", "command": ["true"]}])
        assert hasattr(v, "verify")

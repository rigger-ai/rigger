"""Tests for CiStatusVerifier."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from rigger._types import TaskResult, VerifyAction
from rigger.verifiers.ci_status import CiStatusVerifier


@pytest.fixture
def result() -> TaskResult:
    return TaskResult(task_id="t1", status="success")


class TestPassingCI:
    @patch("rigger.verifiers.ci_status.subprocess.run")
    def test_accept_on_success(self, mock_run, tmp_path: Path, result: TaskResult):
        # First call: git rev-parse (branch detection)
        # Second call: gh run list (status check)
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 0, stdout="feature/t1\n", stderr=""),
            subprocess.CompletedProcess(
                [],
                0,
                stdout=json.dumps([{"status": "completed", "conclusion": "success"}]),
                stderr="",
            ),
        ]
        v = CiStatusVerifier(timeout=5, poll_interval=1)
        vr = v.verify(tmp_path, result)
        assert vr.passed is True
        assert vr.action == VerifyAction.ACCEPT

    @patch("rigger.verifiers.ci_status.subprocess.run")
    def test_explicit_branch(self, mock_run, tmp_path: Path, result: TaskResult):
        mock_run.return_value = subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps([{"status": "completed", "conclusion": "success"}]),
            stderr="",
        )
        v = CiStatusVerifier(branch="main", timeout=5, poll_interval=1)
        vr = v.verify(tmp_path, result)
        assert vr.passed is True


class TestFailingCI:
    @patch("rigger.verifiers.ci_status.subprocess.run")
    def test_retry_on_failure(self, mock_run, tmp_path: Path, result: TaskResult):
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 0, stdout="main\n", stderr=""),
            subprocess.CompletedProcess(
                [],
                0,
                stdout=json.dumps([{"status": "completed", "conclusion": "failure"}]),
                stderr="",
            ),
            # gh run list for logs
            subprocess.CompletedProcess(
                [],
                0,
                stdout=json.dumps([{"databaseId": 123}]),
                stderr="",
            ),
            # gh run view --log-failed
            subprocess.CompletedProcess([], 0, stdout="Error in step 3", stderr=""),
        ]
        v = CiStatusVerifier(timeout=5, poll_interval=1)
        vr = v.verify(tmp_path, result)
        assert vr.passed is False
        assert vr.action == VerifyAction.RETRY


class TestTimeout:
    @patch("rigger.verifiers.ci_status.time.sleep")
    @patch("rigger.verifiers.ci_status.subprocess.run")
    def test_timeout_on_pending(
        self, mock_run, mock_sleep, tmp_path: Path, result: TaskResult
    ):
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 0, stdout="main\n", stderr=""),
            subprocess.CompletedProcess(
                [],
                0,
                stdout=json.dumps([{"status": "in_progress"}]),
                stderr="",
            ),
        ]
        v = CiStatusVerifier(timeout=1, poll_interval=2)
        vr = v.verify(tmp_path, result)
        assert vr.passed is False
        assert "timeout" in vr.message.lower() or "pending" in vr.message.lower()


class TestBranchDetection:
    @patch("rigger.verifiers.ci_status.subprocess.run")
    def test_block_on_no_branch(self, mock_run, tmp_path: Path, result: TaskResult):
        mock_run.return_value = subprocess.CompletedProcess(
            [], 1, stdout="", stderr="not a git repo"
        )
        v = CiStatusVerifier(timeout=5)
        vr = v.verify(tmp_path, result)
        assert vr.passed is False
        assert vr.action == VerifyAction.BLOCK


class TestActionRouting:
    @patch("rigger.verifiers.ci_status.subprocess.run")
    def test_custom_action_on_fail(self, mock_run, tmp_path: Path, result: TaskResult):
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 0, stdout="main\n", stderr=""),
            subprocess.CompletedProcess(
                [],
                0,
                stdout=json.dumps([{"status": "completed", "conclusion": "failure"}]),
                stderr="",
            ),
            subprocess.CompletedProcess(
                [],
                0,
                stdout=json.dumps([{"databaseId": 1}]),
                stderr="",
            ),
            subprocess.CompletedProcess([], 0, stdout="logs", stderr=""),
        ]
        v = CiStatusVerifier(timeout=5, poll_interval=1, action_on_fail="escalate")
        vr = v.verify(tmp_path, result)
        assert vr.action == VerifyAction.ESCALATE


class TestProtocolConformance:
    def test_satisfies_verifier_protocol(self):
        from rigger._protocols import Verifier

        v: Verifier = CiStatusVerifier(timeout=5)
        assert hasattr(v, "verify")

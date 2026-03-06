"""Tests for AtomicIssueTaskSource."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rigger._types import TaskResult
from rigger.task_sources.atomic_issue import AtomicIssueTaskSource


class TestConstruction:
    def test_github_defaults(self):
        src = AtomicIssueTaskSource(provider="github", issue_id="owner/repo#42")
        assert src._provider == "github"
        assert src._api_key_env == "GITHUB_TOKEN"

    def test_linear_defaults(self):
        src = AtomicIssueTaskSource(provider="linear", issue_id="uuid-123")
        assert src._provider == "linear"
        assert src._api_key_env == "LINEAR_API_KEY"

    def test_invalid_provider_raises(self):
        with pytest.raises(ValueError, match="Unsupported provider"):
            AtomicIssueTaskSource(provider="jira", issue_id="X-1")


class TestGitHubPending:
    def test_returns_open_issue(self):
        src = AtomicIssueTaskSource(provider="github", issue_id="org/repo#10")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "id": 12345,
            "title": "Fix the thing",
            "body": "Details here",
            "state": "open",
            "labels": [{"name": "bug"}],
            "html_url": "https://github.com/org/repo/issues/10",
        }
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test"}),
            patch("rigger.task_sources.atomic_issue.httpx.Client") as mock_cls,
        ):
            mock_client = MagicMock()
            mock_client.get.return_value = mock_resp
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            tasks = src.pending(Path("/p"))

        assert len(tasks) == 1
        assert tasks[0].description == "Fix the thing"
        assert tasks[0].metadata["provider"] == "github"
        assert tasks[0].metadata["number"] == 10

    def test_closed_issue_returns_empty(self):
        src = AtomicIssueTaskSource(provider="github", issue_id="org/repo#10")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 12345, "state": "closed"}
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test"}),
            patch("rigger.task_sources.atomic_issue.httpx.Client") as mock_cls,
        ):
            mock_client = MagicMock()
            mock_client.get.return_value = mock_resp
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            tasks = src.pending(Path("/p"))

        assert tasks == []

    def test_bare_number_with_repo_param(self):
        src = AtomicIssueTaskSource(provider="github", issue_id="42", repo="org/repo")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "id": 999,
            "title": "Task",
            "state": "open",
            "labels": [],
            "body": "",
            "html_url": "",
        }
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test"}),
            patch("rigger.task_sources.atomic_issue.httpx.Client") as mock_cls,
        ):
            mock_client = MagicMock()
            mock_client.get.return_value = mock_resp
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            tasks = src.pending(Path("/p"))

        assert len(tasks) == 1

    def test_bare_number_without_repo_returns_empty(self):
        src = AtomicIssueTaskSource(provider="github", issue_id="42")
        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test"}):
            tasks = src.pending(Path("/p"))
        assert tasks == []


class TestGitHubMarkComplete:
    def test_closes_issue(self):
        src = AtomicIssueTaskSource(provider="github", issue_id="org/repo#10")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test"}),
            patch("rigger.task_sources.atomic_issue.httpx.Client") as mock_cls,
        ):
            mock_client = MagicMock()
            mock_client.patch.return_value = mock_resp
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = TaskResult(task_id="12345", status="success")
            src.mark_complete("12345", result)

        assert src._done is True


class TestMissingApiKey:
    def test_pending_returns_empty(self):
        src = AtomicIssueTaskSource(provider="github", issue_id="org/repo#1")
        with patch.dict("os.environ", {}, clear=True):
            assert src.pending(Path("/p")) == []

    def test_mark_complete_noop(self):
        src = AtomicIssueTaskSource(provider="github", issue_id="org/repo#1")
        with patch.dict("os.environ", {}, clear=True):
            result = TaskResult(task_id="x", status="success")
            src.mark_complete("x", result)  # Should not raise
            assert src._done is True


class TestIdempotency:
    def test_pending_empty_after_mark_complete(self):
        src = AtomicIssueTaskSource(provider="github", issue_id="org/repo#10")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test"}),
            patch("rigger.task_sources.atomic_issue.httpx.Client") as mock_cls,
        ):
            mock_client = MagicMock()
            mock_client.patch.return_value = mock_resp
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = TaskResult(task_id="12345", status="success")
            src.mark_complete("12345", result)

        # No API call needed — already marked done internally
        assert src.pending(Path("/p")) == []


class TestProtocolConformance:
    def test_satisfies_task_source_protocol(self):
        from rigger._protocols import TaskSource

        source: TaskSource = AtomicIssueTaskSource(
            provider="github", issue_id="org/repo#1"
        )
        assert hasattr(source, "pending")
        assert hasattr(source, "mark_complete")

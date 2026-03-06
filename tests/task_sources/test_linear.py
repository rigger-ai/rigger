"""Tests for LinearTaskSource."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rigger._types import TaskResult
from rigger.task_sources.linear import LinearTaskSource


@pytest.fixture
def linear_src() -> LinearTaskSource:
    return LinearTaskSource(team="ENG", project="MyProject", labels=["bug"])


def _mock_issues_response() -> dict:
    return {
        "data": {
            "team": {
                "issues": {
                    "nodes": [
                        {
                            "id": "issue-1",
                            "identifier": "ENG-1",
                            "title": "Fix crash",
                            "description": "App crashes on startup",
                            "priority": 1,
                            "state": {
                                "name": "Todo",
                                "type": "unstarted",
                            },
                            "labels": {"nodes": [{"name": "bug"}]},
                        },
                        {
                            "id": "issue-2",
                            "identifier": "ENG-2",
                            "title": "Add feature",
                            "description": "New feature",
                            "priority": 3,
                            "state": {
                                "name": "Todo",
                                "type": "unstarted",
                            },
                            "labels": {"nodes": []},
                        },
                    ]
                }
            }
        }
    }


def _mock_done_state_response() -> dict:
    return {
        "data": {"team": {"states": {"nodes": [{"id": "state-done", "name": "Done"}]}}}
    }


def _mock_transition_response() -> dict:
    return {
        "data": {
            "issueUpdate": {
                "success": True,
                "issue": {
                    "id": "issue-1",
                    "state": {"name": "Done"},
                },
            }
        }
    }


def _setup_mock_client(mock_cls, mock_resp):
    """Wire up httpx.Client context manager mock."""
    client = MagicMock()
    client.post.return_value = mock_resp
    mock_cls.return_value.__enter__ = MagicMock(return_value=client)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return client


class TestPending:
    def test_returns_issues_as_tasks(self, linear_src: LinearTaskSource):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _mock_issues_response()
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.dict("os.environ", {"LINEAR_API_KEY": "test-key"}),
            patch("rigger.task_sources.linear.httpx.Client") as mock_cls,
        ):
            _setup_mock_client(mock_cls, mock_resp)
            tasks = linear_src.pending(Path("/project"))

        assert len(tasks) == 2
        assert tasks[0].id == "issue-1"
        assert tasks[0].description == "Fix crash"
        assert tasks[0].metadata["priority"] == 1
        assert tasks[0].metadata["labels"] == ["bug"]
        assert tasks[1].id == "issue-2"

    def test_missing_api_key_returns_empty(self, linear_src: LinearTaskSource):
        with patch.dict("os.environ", {}, clear=True):
            tasks = linear_src.pending(Path("/project"))
        assert tasks == []

    def test_api_error_returns_empty(self, linear_src: LinearTaskSource):
        import httpx

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500",
            request=MagicMock(),
            response=MagicMock(),
        )

        with (
            patch.dict("os.environ", {"LINEAR_API_KEY": "test-key"}),
            patch("rigger.task_sources.linear.httpx.Client") as mock_cls,
        ):
            _setup_mock_client(mock_cls, mock_resp)
            tasks = linear_src.pending(Path("/project"))

        assert tasks == []

    def test_graphql_error_returns_empty(self, linear_src: LinearTaskSource):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"errors": [{"message": "Bad query"}]}
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.dict("os.environ", {"LINEAR_API_KEY": "test-key"}),
            patch("rigger.task_sources.linear.httpx.Client") as mock_cls,
        ):
            _setup_mock_client(mock_cls, mock_resp)
            tasks = linear_src.pending(Path("/project"))

        assert tasks == []


class TestMarkComplete:
    def test_transitions_to_done(self, linear_src: LinearTaskSource):
        call_count = 0

        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if call_count == 1:
                resp.json.return_value = _mock_done_state_response()
            else:
                resp.json.return_value = _mock_transition_response()
            return resp

        with (
            patch.dict("os.environ", {"LINEAR_API_KEY": "test-key"}),
            patch("rigger.task_sources.linear.httpx.Client") as mock_cls,
        ):
            client = MagicMock()
            client.post = mock_post
            mock_cls.return_value.__enter__ = MagicMock(return_value=client)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = TaskResult(task_id="issue-1", status="success")
            linear_src.mark_complete("issue-1", result)

        # done state query + transition mutation
        assert call_count == 2

    def test_missing_api_key_noop(self, linear_src: LinearTaskSource):
        with patch.dict("os.environ", {}, clear=True):
            result = TaskResult(task_id="issue-1", status="success")
            # Should not raise
            linear_src.mark_complete("issue-1", result)


class TestProtocolConformance:
    def test_satisfies_task_source_protocol(self):
        from rigger._protocols import TaskSource

        source: TaskSource = LinearTaskSource(team="ENG")
        assert hasattr(source, "pending")
        assert hasattr(source, "mark_complete")

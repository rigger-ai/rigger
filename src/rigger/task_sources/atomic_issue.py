"""AtomicIssueTaskSource — one GitHub or Linear issue = one task.

Config name: ``atomic_issue``

Corpus pattern TD-5: Atomic issue-to-PR dispatch.
Sources: C14 (Composio), C4 (Linear), C12 (SWE-agent).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import httpx

from rigger._types import Task, TaskResult

logger = logging.getLogger(__name__)


class AtomicIssueTaskSource:
    """One issue = one task, no decomposition.

    Fetches a single issue from GitHub or Linear and surfaces it as the
    sole pending task. ``mark_complete`` closes or transitions the issue.

    Args:
        provider: ``"github"`` or ``"linear"``.
        issue_id: Issue identifier. For GitHub: ``"owner/repo#123"`` or
            just ``"123"`` (requires ``repo`` param). For Linear: the
            issue UUID.
        api_key_env: Environment variable containing the API token.
        repo: GitHub repo in ``"owner/repo"`` format (optional, used
            when ``issue_id`` is a bare number).
    """

    def __init__(  # noqa: D107
        self,
        provider: str,
        issue_id: str,
        api_key_env: str = "",
        repo: str = "",
    ) -> None:
        if provider not in ("github", "linear"):
            msg = f"Unsupported provider: {provider!r}. Use 'github' or 'linear'."
            raise ValueError(msg)
        self._provider = provider
        self._issue_id = issue_id
        self._api_key_env = api_key_env or (
            "GITHUB_TOKEN" if provider == "github" else "LINEAR_API_KEY"
        )
        self._repo = repo
        self._done = False

    def pending(self, project_root: Path) -> list[Task]:
        """Return the single issue as a Task, or empty if already done."""
        if self._done:
            return []

        api_key = os.environ.get(self._api_key_env, "")
        if not api_key:
            logger.warning("API key not found in env var %s", self._api_key_env)
            return []

        try:
            if self._provider == "github":
                return self._fetch_github(api_key)
            return self._fetch_linear(api_key)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning("Failed to fetch issue %s: %s", self._issue_id, exc)
            return []

    def mark_complete(self, task_id: str, result: TaskResult) -> None:
        """Close the issue on the remote provider."""
        api_key = os.environ.get(self._api_key_env, "")
        if not api_key:
            logger.warning("API key not found in env var %s", self._api_key_env)
            self._done = True
            return

        try:
            if self._provider == "github":
                self._close_github(api_key)
            else:
                self._close_linear(api_key, task_id)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning("Failed to close issue %s: %s", self._issue_id, exc)

        self._done = True

    # ── GitHub ──────────────────────────────────────────────────

    def _parse_github_ref(self) -> tuple[str, int]:
        """Parse owner/repo and issue number from issue_id."""
        if "#" in self._issue_id:
            repo_part, num_part = self._issue_id.rsplit("#", 1)
            return repo_part, int(num_part)
        if self._repo:
            return self._repo, int(self._issue_id)
        msg = (
            "GitHub issue_id must be 'owner/repo#123' or provide repo param. "
            f"Got: {self._issue_id!r}"
        )
        raise ValueError(msg)

    def _fetch_github(self, api_key: str) -> list[Task]:
        repo, number = self._parse_github_ref()
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"https://api.github.com/repos/{repo}/issues/{number}",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()

        if data.get("state") == "closed":
            self._done = True
            return []

        return [
            Task(
                id=str(data["id"]),
                description=data.get("title", ""),
                metadata={
                    "provider": "github",
                    "repo": repo,
                    "number": number,
                    "body": data.get("body", ""),
                    "labels": [lbl["name"] for lbl in data.get("labels", [])],
                    "url": data.get("html_url", ""),
                },
            )
        ]

    def _close_github(self, api_key: str) -> None:
        repo, number = self._parse_github_ref()
        with httpx.Client(timeout=30) as client:
            resp = client.patch(
                f"https://api.github.com/repos/{repo}/issues/{number}",
                json={"state": "closed"},
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            resp.raise_for_status()

    # ── Linear ──────────────────────────────────────────────────

    def _fetch_linear(self, api_key: str) -> list[Task]:
        query = """
        query($id: String!) {
          issue(id: $id) {
            id identifier title description priority
            state { name type }
          }
        }
        """
        data = self._linear_graphql(api_key, query, {"id": self._issue_id})
        issue = data.get("data", {}).get("issue")
        if not issue:
            return []

        state_type = issue.get("state", {}).get("type", "")
        if state_type in ("completed", "canceled"):
            self._done = True
            return []

        return [
            Task(
                id=issue["id"],
                description=issue.get("title", ""),
                metadata={
                    "provider": "linear",
                    "identifier": issue.get("identifier", ""),
                    "priority": issue.get("priority", 4),
                    "description_body": issue.get("description", ""),
                    "state": issue.get("state", {}).get("name", ""),
                },
            )
        ]

    def _close_linear(self, api_key: str, task_id: str) -> None:
        # Find the team's completed state
        # We use the issue's team info from the issue query
        state_query = """
        query($issueId: String!) {
          issue(id: $issueId) {
            team {
              states(filter: { type: { eq: "completed" } }) {
                nodes { id name }
              }
            }
          }
        }
        """
        data = self._linear_graphql(api_key, state_query, {"issueId": task_id})
        states = (
            data.get("data", {})
            .get("issue", {})
            .get("team", {})
            .get("states", {})
            .get("nodes", [])
        )
        if not states:
            logger.warning("No completed state found for Linear issue %s", task_id)
            return

        mutation = """
        mutation($issueId: String!, $stateId: String!) {
          issueUpdate(id: $issueId, input: { stateId: $stateId }) {
            success
          }
        }
        """
        self._linear_graphql(
            api_key, mutation, {"issueId": task_id, "stateId": states[0]["id"]}
        )

    @staticmethod
    def _linear_graphql(
        api_key: str, query: str, variables: dict[str, Any]
    ) -> dict[str, Any]:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                "https://api.linear.app/graphql",
                json={"query": query, "variables": variables},
                headers={
                    "Authorization": api_key,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            body: dict[str, Any] = resp.json()
            if "errors" in body:
                msg = body["errors"][0].get("message", "Unknown GraphQL error")
                raise ValueError(msg)
            return body

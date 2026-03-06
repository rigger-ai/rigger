"""LinearTaskSource — queries the Linear API for issues matching filters.

Config name: ``linear``

Corpus pattern TD-3: External issue tracker as backlog.
Source: C4 (Linear Coding Agent Harness).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import httpx

from rigger._types import Task, TaskResult

logger = logging.getLogger(__name__)

_GRAPHQL_ENDPOINT = "https://api.linear.app/graphql"

_ISSUES_QUERY = """
query($teamKey: String!, $projectName: String, $labels: [String!]) {
  team(key: $teamKey) {
    issues(
      filter: {
        state: { type: { nin: ["completed", "canceled"] } }
        project: { name: { eq: $projectName } }
        labels: { name: { in: $labels } }
      }
      orderBy: priority
      first: 50
    ) {
      nodes {
        id
        identifier
        title
        description
        priority
        state { name type }
        labels { nodes { name } }
      }
    }
  }
}
"""

_TRANSITION_QUERY = """
mutation($issueId: String!, $stateId: String!) {
  issueUpdate(id: $issueId, input: { stateId: $stateId }) {
    success
    issue { id state { name } }
  }
}
"""

_DONE_STATE_QUERY = """
query($teamKey: String!) {
  team(key: $teamKey) {
    states(filter: { type: { eq: "completed" } }) {
      nodes { id name }
    }
  }
}
"""


class LinearTaskSource:
    """Queries Linear API for issues matching filters, ordered by priority.

    Uses httpx for API calls (no Linear SDK dependency). The API key is
    read from an environment variable at call time.

    Args:
        team: Linear team key (e.g., ``"ENG"``).
        project: Optional project name filter.
        labels: Optional label name filter.
        api_key_env: Environment variable containing the Linear API key.
    """

    def __init__(  # noqa: D107
        self,
        team: str,
        project: str | None = None,
        labels: list[str] | None = None,
        api_key_env: str = "LINEAR_API_KEY",
    ) -> None:
        self._team = team
        self._project = project
        self._labels = labels
        self._api_key_env = api_key_env

    def pending(self, project_root: Path) -> list[Task]:
        """Return Linear issues ordered by priority (urgent first)."""
        api_key = os.environ.get(self._api_key_env, "")
        if not api_key:
            logger.warning("Linear API key not found in env var %s", self._api_key_env)
            return []

        variables: dict[str, Any] = {"teamKey": self._team}
        if self._project:
            variables["projectName"] = self._project
        if self._labels:
            variables["labels"] = self._labels

        try:
            data = self._graphql(api_key, _ISSUES_QUERY, variables)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning("Linear API request failed: %s", exc)
            return []

        nodes = data.get("data", {}).get("team", {}).get("issues", {}).get("nodes", [])

        return [
            Task(
                id=issue["id"],
                description=issue.get("title", ""),
                metadata={
                    "identifier": issue.get("identifier", ""),
                    "priority": issue.get("priority", 4),
                    "description_body": issue.get("description", ""),
                    "state": issue.get("state", {}).get("name", ""),
                    "labels": [
                        lbl["name"] for lbl in issue.get("labels", {}).get("nodes", [])
                    ],
                },
            )
            for issue in nodes
        ]

    def mark_complete(self, task_id: str, result: TaskResult) -> None:
        """Transition issue to the team's 'Done' state."""
        api_key = os.environ.get(self._api_key_env, "")
        if not api_key:
            logger.warning("Linear API key not found in env var %s", self._api_key_env)
            return

        try:
            done_state_id = self._get_done_state_id(api_key)
            if not done_state_id:
                logger.warning("No completed state found for team %s", self._team)
                return
            self._graphql(
                api_key,
                _TRANSITION_QUERY,
                {"issueId": task_id, "stateId": done_state_id},
            )
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning("Failed to mark Linear issue %s as done: %s", task_id, exc)

    def _get_done_state_id(self, api_key: str) -> str | None:
        """Fetch the first completed-type state ID for the team."""
        data = self._graphql(api_key, _DONE_STATE_QUERY, {"teamKey": self._team})
        states = data.get("data", {}).get("team", {}).get("states", {}).get("nodes", [])
        if states:
            return states[0]["id"]
        return None

    @staticmethod
    def _graphql(api_key: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Execute a GraphQL request against the Linear API."""
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                _GRAPHQL_ENDPOINT,
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
